/**
 * Balance checker extension.
 *
 * Automatically shows the active provider's account balance in the footer
 * status bar, and provides a /balance command for a detailed manual check.
 *
 * Provider is auto-detected from the active model, so it adapts automatically:
 *   - OpenRouter  -> GET /api/v1/auth/key  (limit_remaining, the real spendable
 *                    limit for THIS key)
 *   - DeepSeek    -> GET /api/v1/user/balance (total_balance)
 *   - CodeBuddy   -> GET /v3/config (no public balance endpoint; lists model
 *                    credit pricing instead)
 *
 * Usage:
 *   /balance                 -> detailed check of the current provider
 *   /balance deepseek        -> force-check a specific provider
 *   /balance openrouter      -> force-check a specific provider
 *   /balance codebuddy       -> force-check a specific provider
 *
 * The API key / auth is resolved through pi's normal credential chain
 * (CLI --api-key, auth.json, or environment variable), so no secret is stored
 * here. CodeBuddy uses its OAuth-derived headers (x-domain, x-user-id, ...).
 */
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

// Minimum gap between automatic refreshes, to avoid hammering the balance
// API during long runs of rapid turns. Balance only changes when the model
// is used, so we refresh on session start, model change, and after each
// settled agent run instead of using a timer.
const MIN_AUTO_REFRESH_MS = 60 * 1000;

interface EndpointConfig {
	base: string;
	url: string;
	/** "api_key" -> only Bearer token is needed; "oauth_headers" -> resolved provider headers required. */
	auth: "api_key" | "oauth_headers";
	parse: (json: any, preferId?: string) => string[];
}

const ENDPOINTS: Record<string, EndpointConfig> = {
	openrouter: {
		// /credits returns the account-level lifetime ledger, which is misleading
		// for "how much can I spend". /auth/key reports the real spendable limit
		// for THIS key (limit_remaining), so we use that as the balance.
		base: "https://openrouter.ai",
		url: "/api/v1/auth/key",
		auth: "api_key",
		parse: (json) => {
			const d = json?.data ?? {};
			const remaining = d.limit_remaining != null ? Number(d.limit_remaining) : NaN;
			const limit = d.limit != null ? Number(d.limit) : NaN;
			const reset = d.limit_reset ?? "";
			const usage = d.usage != null ? Number(d.usage) : NaN;
			const limPart = Number.isFinite(limit) ? `/ ${limit.toFixed(2)}${reset ? "/" + reset : ""}` : "";
			const lines = [];
			if (Number.isFinite(remaining)) lines.push(`Remaining limit: \$${remaining.toFixed(2)} ${limPart}`.trim());
			if (Number.isFinite(usage)) lines.push(`Spent: \$${usage.toFixed(2)}`);
			return lines.length > 0 ? lines : ["No data"];
		},
	},
	deepseek: {
		base: "https://api.deepseek.com",
		url: "/user/balance",
		auth: "api_key",
		parse: (json) => {
			const infos: Array<{ currency?: string; total_balance?: string; granted_balance?: string; topped_up_balance?: string }> =
				json?.balance_infos ?? [];
			if (infos.length === 0) {
				return [`Available: ${json?.is_available === true ? "yes" : "no"}`];
			}
			return infos.map((b) => {
				const cur = b.currency ?? "";
				const parts = [];
				if (b.total_balance != null) parts.push(`Total ${b.total_balance}`);
				if (b.topped_up_balance != null) parts.push(`topped up ${b.topped_up_balance}`);
				if (b.granted_balance != null) parts.push(`granted ${b.granted_balance}`);
				return `Balance${cur ? ` (${cur})` : ""}: ${parts.join(", ") || "n/a"}`;
			});
		},
	},
	codebuddy: {
		// CodeBuddy's coding gateway exposes no account balance endpoint, so we
		// list per-model credit pricing from the live product config instead.
		base: "https://copilot.tencent.com",
		url: "/v3/config",
		auth: "oauth_headers",
		parse: (json, preferId) => {
			const models: Array<{ id?: string; name?: string; credits?: string }> =
				json?.data?.models ?? [];
			const ds = models.filter((m) => typeof m?.id === "string" && m.id.includes("deepseek"));
			const lines = ds.map((m) => `${m.name ?? m.id}: ${m.credits ?? "n/a"}`);
			// The footer shows lines[0]; put the currently active model's price
			// first so the footer reflects the model actually in use, not the
			// arbitrary order of the models array.
			if (preferId) {
				const idx = ds.findIndex((m) => m.id === preferId);
				if (idx > 0) {
					const [line] = lines.splice(idx, 1);
					lines.unshift(line);
				}
			}
			lines.push(`${models.length} models total`);
			return lines;
		},
	},
};

function providerName(provider: string): string {
	return provider.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

interface ResolvedAuth {
	apiKey: string;
	headers: Record<string, string>;
}

async function resolveAuth(
	ctx: ExtensionContext,
	provider: string,
	cfg: EndpointConfig,
): Promise<ResolvedAuth | undefined> {
	if (cfg.auth === "oauth_headers") {
		const auth = await ctx.modelRegistry.getProviderAuth(provider).catch(() => undefined);
		const apiKey = auth?.auth?.apiKey;
		if (!apiKey) return undefined;
		return {
			apiKey,
			headers: { ...(auth.auth.headers ?? {}) },
		};
	}
	const apiKey = await ctx.modelRegistry.getApiKeyForProvider(provider).catch(() => undefined);
	if (!apiKey) return undefined;
	return { apiKey, headers: {} };
}

async function fetchBalance(
	cfg: EndpointConfig,
	auth: ResolvedAuth,
	preferId?: string,
): Promise<string[]> {
	const url = cfg.url.startsWith("http") ? cfg.url : cfg.base + cfg.url;
	const controller = new AbortController();
	const timer = setTimeout(() => controller.abort(), 15000);
	try {
		const res = await fetch(url, {
			headers: {
				...auth.headers,
				Authorization: `Bearer ${auth.apiKey}`,
				Accept: "application/json",
			},
			signal: controller.signal,
		});
		if (!res.ok) {
			const body = await res.text().catch(() => "");
			return [`Request failed with HTTP ${res.status}: ${body.slice(0, 200)}`];
		}
		const json = await res.json().catch(() => ({}));
		return cfg.parse(json, preferId);
	} finally {
		clearTimeout(timer);
	}
}

export default function (pi: ExtensionAPI) {
	let refreshing = false;
	let current: ExtensionContext | undefined;
	let activeProvider = "";
	let lastFetch = 0;

	async function refresh(force = false) {
		if (!current || refreshing) return;
		// Rate-limit automatic refreshes (manual /balance always bypasses).
		if (!force && Date.now() - lastFetch < MIN_AUTO_REFRESH_MS) return;
		refreshing = true;
		try {
			const provider =
				(activeProvider || current.model?.provider?.toLowerCase() || "").trim();
			if (!provider) return;

			// Provider without a known balance endpoint: show it clearly instead
			// of silently keeping a stale balance from a previous provider.
			const cfg = ENDPOINTS[provider];
			if (!cfg) {
				current.ui.setStatus(
					"balance",
					`💳 ${providerName(provider)}: unsupported`,
				);
				return;
			}

			const auth = await resolveAuth(current, provider, cfg);
			lastFetch = Date.now();
			if (!auth) {
				current.ui.setStatus(
					"balance",
					`💳 ${providerName(provider)}: no API key`,
				);
				return;
			}
			const lines = await fetchBalance(cfg, auth, current.model?.id);
			// Show a short "first line" style summary in the footer.
			current.ui.setStatus("balance", `💳 ${providerName(provider)}: ${lines[0] ?? "n/a"}`);
		} catch {
			// silent: transient fetch failures should not spam the footer
		} finally {
			refreshing = false;
		}
	}

	pi.on("session_start", (_e, ctx) => {
		current = ctx;
		activeProvider = ctx.model?.provider?.toLowerCase() ?? "";
		void refresh(true);
	});

	// Balance is provider-scoped, not model-scoped. Only re-query when the
	// provider actually changes; same-provider model switches are already
	// covered by the post-turn agent_settled refresh, so no request here.
	pi.on("model_select", (e, ctx) => {
		current = ctx;
		const newProvider = e.model.provider.toLowerCase();
		const providerChanged = newProvider !== activeProvider;
		activeProvider = newProvider;
		if (providerChanged) void refresh(true);
	});

	// balance changes when the model is used; refresh after a run settles
	pi.on("agent_settled", () => {
		void refresh();
	});

	pi.on("session_shutdown", () => {
		current = undefined;
	});

	pi.registerCommand("balance", {
		description: "Show the current provider's account balance (OpenRouter / DeepSeek / CodeBuddy)",
		handler: async (args, ctx) => {
			const requested = args.trim().toLowerCase();
			const provider = requested && ENDPOINTS[requested] ? requested : ctx.model?.provider?.toLowerCase() ?? "";
			if (!provider) {
				ctx.ui.notify("No active model/provider to check.", "error");
				return;
			}
			const cfg = ENDPOINTS[provider];
			if (!cfg) {
				ctx.ui.notify(
					`No balance endpoint for provider "${provider}" (unsupported).`, "error"
				);
				return;
			}

			ctx.ui.notify(`Checking ${providerName(provider)}...`, "info");

			const auth = await resolveAuth(ctx, provider, cfg);
			if (!auth) {
				ctx.ui.notify(
					`No API key configured for "${provider}". Use /login ${provider} or set its environment variable.`,
					"error",
				);
				return;
			}

			const lines = await fetchBalance(cfg, auth, ctx.model?.id);
			void refresh(true); // sync the footer after a manual detailed check
			const summary = `${providerName(provider)}: ${lines.join(" | ")}`;
			console.log(`\n[balance] ${summary}`);
			ctx.ui.notify(summary, "info");
		},
	});
}

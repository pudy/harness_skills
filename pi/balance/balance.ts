/**
 * Balance checker extension.
 *
 * Automatically shows the active provider's account balance in the footer
 * status bar, and provides a /balance command for a detailed manual check.
 *
 * Provider is auto-detected from the active model, so it adapts automatically:
 *   - OpenRouter  -> GET https://openrouter.ai/api/v1/credits
 *   - DeepSeek    -> GET https://api.deepseek.com/user/balance
 *
 * Usage:
 *   /balance                 -> detailed check of the current provider
 *   /balance deepseek        -> force-check a specific provider
 *   /balance openrouter      -> force-check a specific provider
 *
 * The API key is resolved through pi's normal credential chain (CLI --api-key,
 * auth.json, or environment variable), so no secret is stored here.
 */
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

// Minimum gap between automatic refreshes, to avoid hammering the balance
// API during long runs of rapid turns. Balance only changes when the model
// is used, so we refresh on session start, model change, and after each
// settled agent run instead of using a timer.
const MIN_AUTO_REFRESH_MS = 60 * 1000;

const ENDPOINTS: Record<string, { url: string; parse: (json: any) => string[] }> = {
	openrouter: {
		// /credits returns the account-level lifetime ledger, which is misleading
		// for "how much can I spend". /auth/key reports the real spendable limit
		// for THIS key (limit_remaining), so we use that as the balance.
		url: "https://openrouter.ai/api/v1/auth/key",
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
		url: "https://api.deepseek.com/user/balance",
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
};

function providerName(provider: string): string {
	return provider.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

async function fetchBalance(provider: string, apiKey: string): Promise<string[]> {
	const cfg = ENDPOINTS[provider];
	if (!cfg) return [`No balance endpoint defined for provider "${provider}".`];

	const controller = new AbortController();
	const timer = setTimeout(() => controller.abort(), 15000);
	try {
		const res = await fetch(cfg.url, {
			headers: {
				Authorization: `Bearer ${apiKey}`,
				Accept: "application/json",
			},
			signal: controller.signal,
		});
		if (!res.ok) {
			const body = await res.text().catch(() => "");
			return [`Request failed with HTTP ${res.status}: ${body.slice(0, 200)}`];
		}
		const json = await res.json().catch(() => ({}));
		return cfg.parse(json);
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
			if (!provider || !ENDPOINTS[provider]) return;

			const apiKey = await current.modelRegistry
				.getApiKeyForProvider(provider)
				.catch(() => undefined);
			lastFetch = Date.now();
			if (!apiKey) {
				current.ui.setStatus(
					"balance",
					`💳 ${providerName(provider)}: no API key`,
				);
				return;
			}
			const lines = await fetchBalance(provider, apiKey);
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
		description: "Show the current provider's account balance (OpenRouter / DeepSeek)",
		handler: async (args, ctx) => {
			const requested = args.trim().toLowerCase();
			const provider = requested && ENDPOINTS[requested] ? requested : ctx.model?.provider?.toLowerCase() ?? "";
			if (!provider) {
				ctx.ui.notify("No active model/provider to check.", "error");
				return;
			}

			ctx.ui.notify(`Checking ${providerName(provider)} balance...`, "info");

			const apiKey = await ctx.modelRegistry.getApiKeyForProvider(provider).catch(() => undefined);
			if (!apiKey) {
				ctx.ui.notify(
					`No API key configured for "${provider}". Use /login ${provider} or set its environment variable.`,
					"error",
				);
				return;
			}

			const lines = await fetchBalance(provider, apiKey);
			void refresh(true); // sync the footer after a manual detailed check
			const summary = `${providerName(provider)}: ${lines.join(" | ")}`;
			console.log(`\n[balance] ${summary}`);
			ctx.ui.notify(summary, "info");
		},
	});
}

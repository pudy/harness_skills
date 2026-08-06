import { readFile } from "node:fs/promises"
import { homedir } from "node:os"
import { join } from "node:path"
import { createSignal, onCleanup } from "solid-js"
import { jsx } from "@opentui/solid/jsx-runtime"

const id = "balance"
const OR_BASE = "https://openrouter.ai/api/v1"

async function readAuth() {
  try {
    const authFile = join(homedir(), ".local", "share", "opencode", "auth.json")
    const raw = await readFile(authFile, "utf8")
    const json = JSON.parse(raw)
    const out = {}
    for (const [k, v] of Object.entries(json)) {
      if (v && typeof v === "object" && typeof v.key === "string") out[k] = v.key
    }
    return out
  } catch {
    return {}
  }
}

async function fetchBalance(provider, key, baseURL) {
  try {
    if (provider === "openrouter") {
      const res = await fetch(`${OR_BASE}/auth/key`, { headers: { Authorization: `Bearer ${key}` } })
      if (!res.ok) return { ok: false, label: `HTTP ${res.status}` }
      const data = await res.json()
      const remaining = data?.data?.limit_remaining
      if (typeof remaining === "number") return { ok: true, label: `$${remaining.toFixed(2)}` }
      return { ok: false, label: "n/a" }
    }

    const base = (baseURL ?? "").replace(/\/+$/, "")
    if (!base) return { ok: false, label: "no url" }
    const headers = { Authorization: `Bearer ${key}` }

    const sub = await fetch(`${base}/dashboard/billing/subscription`, { headers })
    let limit
    if (sub.ok) {
      const json = await sub.json()
      limit = json?.soft_limit_usd ?? json?.hard_limit_usd
    }

    const usageRes = await fetch(`${base}/dashboard/billing/usage`, { headers })
    let usedCents
    if (usageRes.ok) {
      const json = await usageRes.json()
      usedCents = json?.total_usage
    }

    if (typeof limit === "number" && typeof usedCents === "number") {
      const rem = Math.max(0, limit - usedCents / 100)
      return { ok: true, label: `$${rem.toFixed(2)}` }
    }
    if (typeof limit === "number") return { ok: true, label: `$${limit.toFixed(2)}` }
    return { ok: false, label: "n/a" }
  } catch (e) {
    const msg = (e && e.message) || String(e)
    return { ok: false, label: `err:${msg.slice(0, 40)}` }
  }
}

const tui = async (api) => {
  const keys = await readAuth()
  const cache = new Map()
  const [bal, setBal] = createSignal({ ok: false, label: "…" })
  let lastModel = ""
  let activeSessionId = undefined

  const show = async (model) => {
    if (!model) return
    if (model === lastModel) return
    lastModel = model
    const provider = model.split("/")[0]
    let result
    if (!keys[provider]) {
      result = { ok: false, label: `${provider}:no key` }
    } else {
      const found = api.state.provider.find((p) => p.id === provider)
      result = await fetchBalance(provider, keys[provider], found?.options?.baseURL)
      cache.set(model, result)
    }
    setBal(result)
  }

  const modelFromSession = (sessionId) => {
    const list = api.state.session.messages(sessionId)
    if (Array.isArray(list)) {
      for (let i = list.length - 1; i >= 0; i--) {
        const m = list[i]
        if (m?.role === "assistant" && m.providerID && m.modelID) {
          return `${m.providerID}/${m.modelID}`
        }
      }
    }
    const s = api.state.session.get(sessionId)
    if (s?.model?.providerID && s.model.modelID) return `${s.model.providerID}/${s.model.modelID}`
    return undefined
  }

  const recompute = async () => {
    const model =
      (activeSessionId !== undefined ? modelFromSession(activeSessionId) : undefined) ??
      api.state.config.model ??
      ""
    await show(model)
  }

  const sidOf = (e) => e?.properties?.sessionID ?? e?.data?.sessionID ?? e?.sessionID
  const modelOf = (e) => {
    const p = e?.properties?.model ?? e?.data?.model ?? e?.model
    return p?.providerID && p.modelID ? `${p.providerID}/${p.modelID}` : undefined
  }

  const offs = [
    api.event.on("message.updated", (e) => {
      const sid = sidOf(e)
      const info = e?.properties?.info
      if (sid) {
        activeSessionId = sid
        if (info?.providerID && info?.modelID) void show(`${info.providerID}/${info.modelID}`)
        else void recompute()
      }
    }),
    api.event.on("session.updated", (e) => {
      const sid = sidOf(e)
      if (sid) {
        activeSessionId = sid
        void recompute()
      }
    }),
    api.event.on("session.next.model.switched", (e) => {
      const sid = sidOf(e)
      if (sid) {
        activeSessionId = sid
        const m = modelOf(e)
        if (m) void show(m)
        else void recompute()
      }
    }),
  ]
  onCleanup(() => offs.forEach((off) => off()))

  void recompute()

  function View() {
    const theme = api.theme.current
    const fg = bal().ok ? theme.success : theme.textMuted
    return jsx("text", {
      fg,
      children: [
        jsx("span", { style: { fg: theme.textMuted }, children: "bal " }),
        jsx("b", { children: () => bal().label }),
      ],
    })
  }

  api.slots.register({
    order: 500,
    slots: {
      home_prompt_right() {
        return jsx(View, {})
      },
      session_prompt_right() {
        return jsx(View, {})
      },
    },
  })
}

export default { id, tui }

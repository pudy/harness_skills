import { readFile } from "node:fs/promises"
import { homedir } from "node:os"
import { join } from "node:path"
import { createSignal } from "solid-js"
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
  const [bal, setBal] = createSignal({ ok: false, label: "…" })
  let lastModel = ""
  let activeSessionId = undefined
  const CD = 90_000
  let lastFetch = 0

  const apply = (result) => {
    const cur = bal()
    if (cur.label === result.label && cur.ok === result.ok) return
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
    if (s?.model?.providerID && s.model.id) return `${s.model.providerID}/${s.model.id}`
    return undefined
  }

  const show = async (model, force = false) => {
    if (!model) return
    const provider = model.split("/")[0]
    const modelChanged = model !== lastModel
    if (!modelChanged) {
      if (!force) return
      if (Date.now() - lastFetch < CD) return
    }
    lastModel = model
    lastFetch = Date.now()
    let result
    if (provider === "codebuddy") {
      result = { ok: true, label: "∞" }
    } else if (!keys[provider]) {
      result = { ok: false, label: `${provider}:no key` }
    } else {
      const found = api.state.provider.find((p) => p.id === provider)
      result = await fetchBalance(provider, keys[provider], found?.options?.baseURL)
    }
    if (model !== lastModel) return
    apply(result)
  }

  const activeSid = () => {
    const r = api.route.current
    if (r?.name === "session") return r.params?.sessionID
    return activeSessionId
  }

  const refresh = (force = false) => {
    const sid = activeSid()
    const model =
      (sid !== undefined ? modelFromSession(sid) : undefined) ??
      api.state.config.model ??
      ""
    void show(model, force)
  }

  api.event.on("session.created", (e) => {
    const sid = e?.data?.sessionID
    if (!sid) return
    activeSessionId = sid
    refresh(true)
  })

  api.event.on("session.status", (e) => {
    const sid = e?.data?.sessionID ?? e?.properties?.sessionID
    const status = e?.data?.status ?? e?.properties?.status
    if (!sid || !status) return
    if (status.type !== "idle" && status.type !== "busy") return
    activeSessionId = sid
    refresh(true)
  })

  api.event.on("message.updated", (e) => {
    const sid = e?.data?.sessionID
    const info = e?.data?.info
    if (!sid) return
    activeSessionId = sid
    if (info?.providerID && info?.modelID) {
      const model = `${info.providerID}/${info.modelID}`
      if (model !== lastModel) void show(model)
    }
  })

  void refresh()

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

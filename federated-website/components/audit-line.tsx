// How an audit entry reads, shared by the admin overview and the audit log.

import type { AuditEntry } from "@/lib/platform-api"

export const SECURITY_ACTIONS = new Set(["login.failed", "login.throttled", "site.revoke", "site.enroll_failed", "site.reissue"])

const VERBS: Record<string, string> = {
  "site.register": "registered",
  "site.import": "imported",
  "site.edit": "edited",
  "site.approve": "approved",
  "site.reject": "rejected",
  "site.kit": "downloaded the kit for",
  "site.enroll": "installed the kit:",
  "site.enroll_failed": "refused a kit key for",
  "site.online": "is online:",
  "site.suspend": "suspended",
  "site.resume": "resumed",
  "site.revoke": "revoked",
  "site.reissue": "re-issued the kit for",
  "login.success": "logged in",
  "login.failed": "failed to log in",
  "login.throttled": "was throttled at login",
  "user.create": "created user",
  "user.update": "updated user",
  "user.password": "changed the password of",
  "user.register": "registered",
  "run.start": "started run",
  "run.stop": "stopped run",
  "model.promote": "promoted",
}

export function actorLabel(e: Pick<AuditEntry, "actor_type" | "actor_id" | "actor_name">): string {
  if (e.actor_name) return e.actor_name
  if (e.actor_type === "site") return "Plant"
  if (e.actor_type === "system") return "System"
  if (e.actor_type === "anonymous") return "Someone"
  return e.actor_id ? `${e.actor_type} ${e.actor_id}` : e.actor_type
}

/** "Admin approved zhanatas-wind-farm-1ded" */
export function sentence(e: AuditEntry): { actor: string; verb: string; target: string | null } {
  const actor = e.action === "site.online" || e.action === "site.enroll" ? "" : actorLabel(e)
  return { actor, verb: VERBS[e.action] ?? e.action, target: e.target }
}

export function targetHref(e: Pick<AuditEntry, "action" | "target">): string | null {
  if (!e.target) return null
  if (e.action.startsWith("site.")) return `/sites/${encodeURIComponent(e.target)}`
  if (e.action.startsWith("run.") || e.action === "model.promote") return `/training/${encodeURIComponent(e.target)}`
  return null
}

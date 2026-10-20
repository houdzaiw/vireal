export function appUserLoginLabel(user: {
  account_type?: string | null
  auth_providers?: string[] | null
}) {
  if (user.auth_providers?.length) return user.auth_providers.join(", ")
  if (user.account_type === "clerk") return "Clerk (method not returned)"
  if (user.account_type === "legacy_test") return "Legacy test"
  return "Unknown"
}

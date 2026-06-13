/**
 * Frontend-only password strength heuristic.
 *
 * Custom (no zxcvbn): scoring is intentionally coarse — backend
 * validation is the source of truth (length >= 8). The meter is a
 * visual nudge, never a submit gate.
 *
 * Score 0..4 buckets:
 *  - 0 weak       : < 8 chars
 *  - 1 fair       : 8..11
 *  - 2 strong     : 12..15 OR has 3+ char classes
 *  - 3 strong     : 12..15 AND has 3+ char classes
 *  - 4 veryStrong : >= 16 AND has 3+ char classes
 */
export type PasswordStrengthLabel = 'weak' | 'fair' | 'strong' | 'veryStrong'

export interface PasswordStrengthResult {
  score: 0 | 1 | 2 | 3 | 4
  label: PasswordStrengthLabel
}

export function passwordStrength(password: string): PasswordStrengthResult {
  const len = password.length
  if (len === 0) return { score: 0, label: 'weak' }
  let score = 0
  if (len >= 8) score += 1
  if (len >= 12) score += 1
  if (len >= 16) score += 1
  const classes = [/[a-z]/, /[A-Z]/, /[0-9]/, /[^A-Za-z0-9]/].reduce(
    (n, re) => n + (re.test(password) ? 1 : 0),
    0,
  )
  if (classes >= 3) score += 1
  const clamped = Math.min(4, Math.max(0, score)) as 0 | 1 | 2 | 3 | 4
  const label: PasswordStrengthLabel =
    clamped <= 0 ? 'weak' : clamped === 1 ? 'fair' : clamped <= 3 ? 'strong' : 'veryStrong'
  return { score: clamped, label }
}

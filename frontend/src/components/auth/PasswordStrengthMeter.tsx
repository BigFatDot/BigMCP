/**
 * PasswordStrengthMeter — 4 horizontal segments + a localised label.
 *
 * Visual nudge only. Backend validation is the source of truth; this
 * component never gates the submit button. Uses Tailwind classes
 * already present in the design system (red/amber/lime/green for the
 * 4 buckets).
 */

import { useTranslation } from 'react-i18next'
import { passwordStrength } from '../../utils/passwordStrength'

interface Props {
  password: string
}

const SEGMENT_COLORS: Record<number, string> = {
  // index → background color applied to "filled" segments
  0: 'bg-red-500',
  1: 'bg-amber-500',
  2: 'bg-lime-500',
  3: 'bg-lime-500',
  4: 'bg-green-600',
}

export function PasswordStrengthMeter({ password }: Props) {
  const { t } = useTranslation('auth')
  const { score, label } = passwordStrength(password)

  // We render 4 segments and fill them up to `score` (1..4). At score 0
  // (empty or under-length) every segment stays grey.
  const filledCount = score
  const filledColor = SEGMENT_COLORS[score] || 'bg-gray-200'

  if (!password) {
    // Don't show anything if the user hasn't typed yet — avoids a
    // distracting "weak" red line on an empty field.
    return null
  }

  return (
    <div className="mt-2" aria-live="polite">
      <div className="flex gap-1" role="meter" aria-valuemin={0} aria-valuemax={4} aria-valuenow={score}>
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            className={`h-1.5 flex-1 rounded ${
              i < filledCount ? filledColor : 'bg-gray-200'
            }`}
          />
        ))}
      </div>
      <p className="mt-1 text-xs text-gray-600">
        {t(`signup.passwordStrength.${label}`)}
      </p>
    </div>
  )
}

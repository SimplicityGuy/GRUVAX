/**
 * OnboardingScreen — 0-profile state on /select (Surface 5, UI-SPEC §Surface 5).
 *
 * Shown when GET /api/session returns profile_count === 0.
 * Heading: "NO COLLECTIONS YET" (Barlow Condensed 900 48px)
 * Body: sentence case, Space Grotesk
 * CTA: "OPEN ADMIN PANEL" → /admin
 *
 * Design tokens only — no hardcoded hex.
 */

import { Link } from 'react-router'
import './picker.css'

export function OnboardingScreen() {
  return (
    <div className="picker-page picker-page--onboarding">
      <h1 className="picker-heading">NO COLLECTIONS YET</h1>
      <p className="onboarding-body">
        To get started, ask the owner to set up a profile in the admin panel,
        then come back here.
      </p>
      <Link to="/admin" className="onboarding-cta">
        OPEN ADMIN PANEL
      </Link>
    </div>
  )
}

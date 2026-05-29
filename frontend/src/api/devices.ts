/**
 * Devices API client — typed fetch wrappers for kiosk pairing + admin device lifecycle.
 *
 * Kiosk endpoints (no PIN required):
 *   POST /api/devices/pairing-codes → {code, expires_at}
 *   GET  /api/devices/me            → {state, profile_id?}
 *
 * Admin endpoints (PIN-gated — require active admin session):
 *   POST   /api/admin/devices/bind          → device summary
 *   GET    /api/admin/devices               → {paired, pending, revoked}
 *   PATCH  /api/admin/devices/{id}          → updated device
 *   POST   /api/admin/devices/{id}/revoke
 *   POST   /api/admin/devices/{id}/reinstate
 *   DELETE /api/admin/devices/{id}
 *
 * Design tokens: n/a (API client only — no UI concerns)
 */

export type DeviceState = 'unpaired' | 'pending' | 'paired' | 'revoked'

export interface PairingCodeResponse {
  code: string
  expires_at: string
}

export interface DeviceMeResponse {
  state: DeviceState
  profile_id?: string | null
}

export interface DeviceRow {
  id: string
  display_name: string
  state: 'pending' | 'paired' | 'revoked'
  profile_id: string | null
  profile_name?: string | null
  last_seen_at: string | null
}

export interface AdminDevicesResponse {
  paired: DeviceRow[]
  pending: DeviceRow[]
  revoked: DeviceRow[]
}

export interface BindDeviceRequest {
  code: string
  profile_id?: string
  display_name?: string
}

export interface BindDeviceError {
  detail: {
    type: 'code_not_found' | 'code_expired' | 'rate_limited'
    message?: string
  }
}

/** POST /api/devices/pairing-codes — issue a new pairing code (kiosk-facing, no PIN). */
export async function postPairingCode(): Promise<PairingCodeResponse> {
  const res = await fetch('/api/devices/pairing-codes', { method: 'POST' })
  if (!res.ok) {
    throw new Error(`Failed to fetch pairing code: ${res.status}`)
  }
  return res.json() as Promise<PairingCodeResponse>
}

/** GET /api/devices/me — get device state for the current fingerprint cookie. */
export async function getDeviceMe(): Promise<DeviceMeResponse> {
  const res = await fetch('/api/devices/me')
  if (!res.ok) {
    throw new Error(`Failed to fetch device state: ${res.status}`)
  }
  return res.json() as Promise<DeviceMeResponse>
}

// ── Admin helpers ───────────────────────────────────────────────────────────

/** GET /api/admin/devices — list all devices grouped by state. */
export async function getAdminDevices(): Promise<AdminDevicesResponse> {
  const res = await fetch('/api/admin/devices')
  if (!res.ok) {
    throw new Error(`Failed to fetch devices: ${res.status}`)
  }
  return res.json() as Promise<AdminDevicesResponse>
}

/** POST /api/admin/devices/bind — bind a pairing code to a device. */
export async function bindDevice(body: BindDeviceRequest): Promise<DeviceRow> {
  const res = await fetch('/api/admin/devices/bind', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({})) as BindDeviceError
    throw Object.assign(new Error('Bind failed'), { status: res.status, detail: err.detail })
  }
  return res.json() as Promise<DeviceRow>
}

/** PATCH /api/admin/devices/{id} — rename device. */
export async function renameDevice(id: string, displayName: string): Promise<void> {
  const res = await fetch(`/api/admin/devices/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ display_name: displayName }),
  })
  if (!res.ok) {
    throw new Error(`Rename failed: ${res.status}`)
  }
}

/** PATCH /api/admin/devices/{id} — change or clear a device's profile binding. */
export async function changeDeviceProfile(id: string, profileId: string | null): Promise<void> {
  const res = await fetch(`/api/admin/devices/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile_id: profileId }),
  })
  if (!res.ok) {
    throw new Error(`Change profile failed: ${res.status}`)
  }
}

/** PATCH /api/admin/devices/{id} with profile_id: null — unbind profile. */
export async function unbindDevice(id: string): Promise<void> {
  return changeDeviceProfile(id, null)
}

/** POST /api/admin/devices/{id}/revoke — revoke a device. */
export async function revokeDevice(id: string): Promise<void> {
  const res = await fetch(`/api/admin/devices/${id}/revoke`, { method: 'POST' })
  if (!res.ok) {
    throw new Error(`Revoke failed: ${res.status}`)
  }
}

/** POST /api/admin/devices/{id}/reinstate — reinstate a revoked device. */
export async function reinstateDevice(id: string): Promise<void> {
  const res = await fetch(`/api/admin/devices/${id}/reinstate`, { method: 'POST' })
  if (!res.ok) {
    throw new Error(`Reinstate failed: ${res.status}`)
  }
}

/** DELETE /api/admin/devices/{id} — permanently delete a device record. */
export async function deleteDevice(id: string): Promise<void> {
  const res = await fetch(`/api/admin/devices/${id}`, { method: 'DELETE' })
  if (!res.ok) {
    throw new Error(`Delete failed: ${res.status}`)
  }
}

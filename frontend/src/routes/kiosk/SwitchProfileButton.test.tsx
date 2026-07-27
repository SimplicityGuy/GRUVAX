/**
 * SwitchProfileButton — visibility rules (gruvax-ocrn).
 *
 * The bug: SWITCH PROFILE was offered on PAIRED devices, where the flow is a
 * silent no-op. unbindProfile() clears only the browse cookie, the device binding
 * overrides it (D3-05), and ProfilePickerCard's post-bind /api/session refetch
 * hands the old profile straight back — so the user picked B, saw "BINDING…", and
 * landed on A with no error. Repeating loops forever.
 *
 * These are behavioural tests against the rendered component, driven through the
 * real sessionStore (setSession with an actual GET /api/session payload shape), so
 * they fail if setSession drops is_device_paired again — which is precisely how the
 * button lost the ability to know it was on a paired device.
 *
 * Tests:
 *   1. 2+ profiles, NOT paired  → button rendered (the D2-09 happy path)
 *   2. 2+ profiles, PAIRED      → button absent (gruvax-ocrn)
 *   3. single profile           → button absent (pre-existing D2-09 rule)
 *   4. setSession retains is_device_paired / device_id from the response
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import { SwitchProfileButton } from "./SwitchProfileButton";
import { useSessionStore } from "../../state/sessionStore";
import type { ProfileSummary, SessionData } from "../../api/session";

function profile(id: string, name: string): ProfileSummary {
  return {
    id,
    display_name: name,
    last_sync_at: null,
    last_sync_status: null,
    last_sync_item_count: null,
    app_token_revoked: false,
  };
}

/** A realistic GET /api/session payload. */
function session(overrides: Partial<SessionData> = {}): SessionData {
  return {
    profile_count: 2,
    bound_profile_id: "aaaaaaaa-0000-0000-0000-000000000001",
    profiles: [
      profile("aaaaaaaa-0000-0000-0000-000000000001", "Alice"),
      profile("bbbbbbbb-0000-0000-0000-000000000002", "Bob"),
    ],
    ...overrides,
  };
}

function renderButton() {
  return render(
    <MemoryRouter>
      <SwitchProfileButton />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  // Reset the store to its initial shape between tests (module-level singleton).
  useSessionStore.setState({
    profileCount: 0,
    boundProfileId: null,
    isDevicePaired: false,
    deviceId: null,
    profiles: [],
    revokePending: false,
    reassignBanner: null,
  });
});

afterEach(() => {
  cleanup();
});

describe("SwitchProfileButton visibility", () => {
  it("renders on a browse-bound screen with 2+ profiles", () => {
    useSessionStore.getState().setSession(session({ is_device_paired: false }));
    renderButton();
    expect(screen.queryByRole("button", { name: /switch profile/i })).not.toBeNull();
  });

  it("is absent on a PAIRED device even with 2+ profiles (gruvax-ocrn)", () => {
    useSessionStore.getState().setSession(session({ is_device_paired: true, device_id: "dev-1" }));
    renderButton();
    expect(screen.queryByRole("button", { name: /switch profile/i })).toBeNull();
  });

  it("is absent on a single-profile deployment (D2-09)", () => {
    useSessionStore.getState().setSession(
      session({
        profile_count: 1,
        profiles: [profile("aaaaaaaa-0000-0000-0000-000000000001", "Alice")],
      }),
    );
    renderButton();
    expect(screen.queryByRole("button", { name: /switch profile/i })).toBeNull();
  });
});

describe("sessionStore.setSession", () => {
  it("retains is_device_paired and device_id (gruvax-ocrn)", () => {
    useSessionStore.getState().setSession(session({ is_device_paired: true, device_id: "dev-42" }));

    const state = useSessionStore.getState();
    expect(state.isDevicePaired).toBe(true);
    expect(state.deviceId).toBe("dev-42");
  });

  it("defaults the device fields when the response omits them", () => {
    useSessionStore.getState().setSession(session());

    const state = useSessionStore.getState();
    expect(state.isDevicePaired).toBe(false);
    expect(state.deviceId).toBeNull();
  });
});

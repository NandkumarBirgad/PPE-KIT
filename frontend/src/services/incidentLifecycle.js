/**
 * M2.2B.5E: Canonical incident lifecycle helpers for frontend views.
 * Enforces the canonical three-state lifecycle: OPEN, ACKNOWLEDGED, RESOLVED.
 * Preserves backward compatibility with legacy backend reviewStatus fields.
 */

export const CANONICAL_STATES = Object.freeze({
  OPEN: 'OPEN',
  ACKNOWLEDGED: 'ACKNOWLEDGED',
  RESOLVED: 'RESOLVED',
});

/**
 * Normalizes an incident object to its canonical lifecycle state.
 * Precedence rule: Prefer backend `status` field when it contains a valid canonical state;
 * otherwise fall back to legacy `reviewStatus`.
 *
 * Mapping table:
 * - PENDING           -> OPEN
 * - REVIEWED          -> ACKNOWLEDGED
 * - ACKNOWLEDGED      -> ACKNOWLEDGED
 * - APPROVED          -> RESOLVED
 * - REJECTED          -> RESOLVED
 * - FALSE_POSITIVE    -> RESOLVED
 * - RESOLVED          -> RESOLVED
 *
 * @param {Object} incident
 * @returns {'OPEN' | 'ACKNOWLEDGED' | 'RESOLVED'}
 */
export function getIncidentCanonicalState(incident) {
  if (!incident || typeof incident !== 'object') {
    return CANONICAL_STATES.OPEN;
  }

  // 1. Prefer modern canonical status
  const rawStatus = String(incident.status || '').trim().toUpperCase();
  if (rawStatus === CANONICAL_STATES.OPEN ||
      rawStatus === CANONICAL_STATES.ACKNOWLEDGED ||
      rawStatus === CANONICAL_STATES.RESOLVED) {
    return rawStatus;
  }

  // 2. Fall back to legacy reviewStatus
  const legacyStatus = String(incident.reviewStatus || '').trim().toUpperCase();
  switch (legacyStatus) {
    case 'RESOLVED':
    case 'APPROVED':
    case 'REJECTED':
    case 'FALSE_POSITIVE':
      return CANONICAL_STATES.RESOLVED;

    case 'REVIEWED':
    case 'ACKNOWLEDGED':
      return CANONICAL_STATES.ACKNOWLEDGED;

    case 'PENDING':
    default:
      return CANONICAL_STATES.OPEN;
  }
}

/**
 * Returns the resolution type for resolved incidents without introducing a 4th state.
 * Distinguishes 'AUTOMATIC', 'FALSE_POSITIVE', and 'MANUAL'.
 *
 * @param {Object} incident
 * @returns {'AUTOMATIC' | 'FALSE_POSITIVE' | 'MANUAL' | null}
 */
export function getIncidentResolutionType(incident) {
  const state = getIncidentCanonicalState(incident);
  if (state !== CANONICAL_STATES.RESOLVED) {
    return null;
  }

  const rawType = String(incident.resolution_type || incident.resolutionType || '').trim().toUpperCase();
  if (rawType.includes('FALSE_POSITIVE')) return 'FALSE_POSITIVE';
  if (rawType.includes('AUTO')) return 'AUTOMATIC';
  if (rawType.includes('MANUAL')) return 'MANUAL';

  // Fallback to legacy reviewStatus if resolution_type is not populated
  const legacy = String(incident.reviewStatus || '').trim().toUpperCase();
  if (legacy === 'FALSE_POSITIVE' || legacy === 'REJECTED') {
    return 'FALSE_POSITIVE';
  }

  return 'MANUAL';
}

/**
 * Human-readable label for resolution types.
 */
export function getResolutionTypeLabel(type) {
  switch (type) {
    case 'AUTOMATIC':
      return 'Auto-Compliance';
    case 'FALSE_POSITIVE':
      return 'False Positive';
    case 'MANUAL':
      return 'Manual Resolution';
    default:
      return 'Resolved';
  }
}

/**
 * Maps a canonical filter selection to backend API query param values.
 * Returns an object with the canonical `status` query parameter,
 * or an empty object if no filter or 'ALL' is selected.
 *
 * @param {string} canonicalFilter - 'OPEN' | 'ACKNOWLEDGED' | 'RESOLVED' | ''
 * @returns {{ status?: string }}
 */
export function mapCanonicalFilterToApi(canonicalFilter) {
  const f = String(canonicalFilter || '').trim().toUpperCase();
  if (f === CANONICAL_STATES.OPEN ||
      f === CANONICAL_STATES.ACKNOWLEDGED ||
      f === CANONICAL_STATES.RESOLVED) {
    return { status: f };
  }
  return {};
}

/**
 * Returns UI formatting and badge properties for an incident.
 */
export function getIncidentStatusBadge(incident) {
  const state = getIncidentCanonicalState(incident);
  const resType = getIncidentResolutionType(incident);

  if (state === CANONICAL_STATES.OPEN) {
    return {
      state,
      resType: null,
      label: 'OPEN',
      subLabel: null,
      badgeClass: 'bg-amber-950/80 text-amber-300 border border-amber-800',
      pillClass: 'bg-amber-500',
    };
  }

  if (state === CANONICAL_STATES.ACKNOWLEDGED) {
    return {
      state,
      resType: null,
      label: 'ACKNOWLEDGED',
      subLabel: 'In Progress',
      badgeClass: 'bg-sky-950/80 text-sky-300 border border-sky-800',
      pillClass: 'bg-sky-500',
    };
  }

  // RESOLVED
  if (resType === 'FALSE_POSITIVE') {
    return {
      state,
      resType,
      label: 'RESOLVED',
      subLabel: 'False Positive',
      badgeClass: 'bg-slate-800 text-slate-300 border border-slate-700',
      pillClass: 'bg-slate-400',
    };
  }

  if (resType === 'AUTOMATIC') {
    return {
      state,
      resType,
      label: 'RESOLVED',
      subLabel: 'Auto-Compliance',
      badgeClass: 'bg-emerald-950/80 text-emerald-300 border border-emerald-800',
      pillClass: 'bg-emerald-400',
    };
  }

  return {
    state,
    resType,
    label: 'RESOLVED',
    subLabel: 'Manual',
    badgeClass: 'bg-emerald-950/80 text-emerald-300 border border-emerald-800',
    pillClass: 'bg-emerald-500',
  };
}

/**
 * Validates a lifecycle mutation action before dispatching.
 */
export function validateLifecycleAction(action, reason) {
  const act = String(action || '').trim().toUpperCase();
  const trimmedReason = String(reason || '').trim();

  if (act === 'ACKNOWLEDGE') {
    return { valid: true, error: null };
  }

  if (act === 'RESOLVE') {
    if (!trimmedReason) {
      return { valid: false, error: 'A resolution reason is mandatory to resolve an incident.' };
    }
    return { valid: true, error: null };
  }

  if (act === 'FALSE_POSITIVE') {
    if (!trimmedReason) {
      return { valid: false, error: 'An explanation is mandatory to mark an incident as a false positive.' };
    }
    return { valid: true, error: null };
  }

  return { valid: false, error: `Unsupported lifecycle action: ${action}` };
}

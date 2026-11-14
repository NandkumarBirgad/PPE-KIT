import test from 'node:test';
import assert from 'node:assert/strict';

import {
  CANONICAL_STATES,
  getIncidentCanonicalState,
  getIncidentResolutionType,
  getResolutionTypeLabel,
  mapCanonicalFilterToApi,
  getIncidentStatusBadge,
  validateLifecycleAction,
} from './incidentLifecycle.js';

test('1. Normalizes legacy reviewStatus values to canonical 3 states', () => {
  // PENDING -> OPEN
  assert.equal(getIncidentCanonicalState({ reviewStatus: 'PENDING' }), CANONICAL_STATES.OPEN);
  assert.equal(getIncidentCanonicalState({ reviewStatus: 'pending' }), CANONICAL_STATES.OPEN);

  // REVIEWED / ACKNOWLEDGED -> ACKNOWLEDGED
  assert.equal(getIncidentCanonicalState({ reviewStatus: 'REVIEWED' }), CANONICAL_STATES.ACKNOWLEDGED);
  assert.equal(getIncidentCanonicalState({ reviewStatus: 'reviewed' }), CANONICAL_STATES.ACKNOWLEDGED);
  assert.equal(getIncidentCanonicalState({ reviewStatus: 'ACKNOWLEDGED' }), CANONICAL_STATES.ACKNOWLEDGED);

  // APPROVED / REJECTED / FALSE_POSITIVE / RESOLVED -> RESOLVED
  assert.equal(getIncidentCanonicalState({ reviewStatus: 'APPROVED' }), CANONICAL_STATES.RESOLVED);
  assert.equal(getIncidentCanonicalState({ reviewStatus: 'REJECTED' }), CANONICAL_STATES.RESOLVED);
  assert.equal(getIncidentCanonicalState({ reviewStatus: 'FALSE_POSITIVE' }), CANONICAL_STATES.RESOLVED);
  assert.equal(getIncidentCanonicalState({ reviewStatus: 'RESOLVED' }), CANONICAL_STATES.RESOLVED);
  assert.equal(getIncidentCanonicalState({ reviewStatus: 'resolved' }), CANONICAL_STATES.RESOLVED);
});

test('2. Prioritizes modern canonical status field over legacy reviewStatus', () => {
  // When status is OPEN, overrides legacy reviewStatus
  assert.equal(
    getIncidentCanonicalState({ status: 'OPEN', reviewStatus: 'REVIEWED' }),
    CANONICAL_STATES.OPEN
  );

  // When status is ACKNOWLEDGED, overrides legacy reviewStatus
  assert.equal(
    getIncidentCanonicalState({ status: 'ACKNOWLEDGED', reviewStatus: 'PENDING' }),
    CANONICAL_STATES.ACKNOWLEDGED
  );

  // When status is RESOLVED, overrides legacy reviewStatus
  assert.equal(
    getIncidentCanonicalState({ status: 'RESOLVED', reviewStatus: 'PENDING' }),
    CANONICAL_STATES.RESOLVED
  );
});

test('3. Fallback for null, empty, or unpopulated incidents is OPEN', () => {
  assert.equal(getIncidentCanonicalState(null), CANONICAL_STATES.OPEN);
  assert.equal(getIncidentCanonicalState(undefined), CANONICAL_STATES.OPEN);
  assert.equal(getIncidentCanonicalState({}), CANONICAL_STATES.OPEN);
  assert.equal(getIncidentCanonicalState({ status: '', reviewStatus: '' }), CANONICAL_STATES.OPEN);
});

test('4. Correctly extracts resolution type without introducing 4th primary state', () => {
  // OPEN or ACKNOWLEDGED incidents must return null
  assert.equal(getIncidentResolutionType({ status: 'OPEN' }), null);
  assert.equal(getIncidentResolutionType({ status: 'ACKNOWLEDGED' }), null);
  assert.equal(getIncidentResolutionType({ reviewStatus: 'PENDING' }), null);

  // RESOLVED incidents return resolution type
  assert.equal(
    getIncidentResolutionType({ status: 'RESOLVED', resolution_type: 'AUTOMATIC_COMPLIANCE' }),
    'AUTOMATIC'
  );
  assert.equal(
    getIncidentResolutionType({ status: 'RESOLVED', resolution_type: 'FALSE_POSITIVE' }),
    'FALSE_POSITIVE'
  );
  assert.equal(
    getIncidentResolutionType({ status: 'RESOLVED', resolution_type: 'MANUAL' }),
    'MANUAL'
  );

  // Legacy fallback when resolution_type is not present
  assert.equal(
    getIncidentResolutionType({ reviewStatus: 'FALSE_POSITIVE' }),
    'FALSE_POSITIVE'
  );
  assert.equal(
    getIncidentResolutionType({ reviewStatus: 'REJECTED' }),
    'FALSE_POSITIVE'
  );
  assert.equal(
    getIncidentResolutionType({ reviewStatus: 'RESOLVED' }),
    'MANUAL'
  );
});

test('5. Validates lifecycle actions and mandatory reasons', () => {
  // ACKNOWLEDGE does not require a reason
  assert.equal(validateLifecycleAction('ACKNOWLEDGE', '').valid, true);
  assert.equal(validateLifecycleAction('ACKNOWLEDGE', 'Shift verified').valid, true);

  // RESOLVE requires non-empty reason
  const resEmpty = validateLifecycleAction('RESOLVE', '');
  assert.equal(resEmpty.valid, false);
  assert.match(resEmpty.error, /resolution reason is mandatory/i);

  const resWhitespace = validateLifecycleAction('RESOLVE', '   ');
  assert.equal(resWhitespace.valid, false);

  const resValid = validateLifecycleAction('RESOLVE', 'Worker handed PPE vest');
  assert.equal(resValid.valid, true);

  // FALSE_POSITIVE requires non-empty reason
  const fpEmpty = validateLifecycleAction('FALSE_POSITIVE', '');
  assert.equal(fpEmpty.valid, false);
  assert.match(fpEmpty.error, /explanation is mandatory/i);

  const fpValid = validateLifecycleAction('FALSE_POSITIVE', 'Shadow cast over hardhat');
  assert.equal(fpValid.valid, true);

  // Unknown action rejected
  const unknown = validateLifecycleAction('REOPEN', 'Reopening');
  assert.equal(unknown.valid, false);
});

test('6. Formats status badge props consistently', () => {
  const openBadge = getIncidentStatusBadge({ status: 'OPEN' });
  assert.equal(openBadge.label, 'OPEN');
  assert.equal(openBadge.state, 'OPEN');

  const ackBadge = getIncidentStatusBadge({ status: 'ACKNOWLEDGED' });
  assert.equal(ackBadge.label, 'ACKNOWLEDGED');
  assert.equal(ackBadge.state, 'ACKNOWLEDGED');

  const resManual = getIncidentStatusBadge({ status: 'RESOLVED', resolution_type: 'MANUAL' });
  assert.equal(resManual.label, 'RESOLVED');
  assert.equal(resManual.subLabel, 'Manual');

  const resAuto = getIncidentStatusBadge({ status: 'RESOLVED', resolution_type: 'AUTOMATIC_COMPLIANCE' });
  assert.equal(resAuto.label, 'RESOLVED');
  assert.equal(resAuto.subLabel, 'Auto-Compliance');

  const resFp = getIncidentStatusBadge({ status: 'RESOLVED', resolution_type: 'FALSE_POSITIVE' });
  assert.equal(resFp.label, 'RESOLVED');
  assert.equal(resFp.subLabel, 'False Positive');
});

test('7. Maps canonical filter selections to API parameters', () => {
  assert.deepEqual(mapCanonicalFilterToApi('OPEN'), { status: 'OPEN' });
  assert.deepEqual(mapCanonicalFilterToApi('open'), { status: 'OPEN' });
  assert.deepEqual(mapCanonicalFilterToApi('ACKNOWLEDGED'), { status: 'ACKNOWLEDGED' });
  assert.deepEqual(mapCanonicalFilterToApi('acknowledged'), { status: 'ACKNOWLEDGED' });
  assert.deepEqual(mapCanonicalFilterToApi('RESOLVED'), { status: 'RESOLVED' });
  assert.deepEqual(mapCanonicalFilterToApi('resolved'), { status: 'RESOLVED' });
  assert.deepEqual(mapCanonicalFilterToApi(''), {});
  assert.deepEqual(mapCanonicalFilterToApi('ALL'), {});
  assert.deepEqual(mapCanonicalFilterToApi(null), {});
  assert.deepEqual(mapCanonicalFilterToApi(undefined), {});
});

/**
 * In-memory session for UI state
 * Not persisted — resets on restart.
 */
const sessions = new Map();

const MAX_ACCOUNTS = 10;

function defaultSession() {
  return {
    // Account setup
    awaitingPhoneForIndex: null,
    // Group Manager state
    gmAccIdx: null,
    gmGroups: [],
    gmGroupId: null,
    gmGroupName: null,
    awaitingNumberForAction: null, // 'promote' | 'demote' | null
  };
}

function getSession(userId) {
  if (!sessions.has(userId)) sessions.set(userId, defaultSession());
  return sessions.get(userId);
}

function updateSession(userId, patch) {
  const s = getSession(userId);
  sessions.set(userId, { ...s, ...patch });
}

function resetSession(userId) {
  sessions.set(userId, defaultSession());
}

module.exports = { getSession, updateSession, resetSession, MAX_ACCOUNTS };

const mongoose = require("mongoose");
const { Schema } = mongoose;

// ─── WhatsApp auth state (stored in MongoDB, no file system needed) ────
const AuthStateSchema = new Schema(
  {
    accountId: { type: String, required: true },
    type: { type: String, required: true },
    data: { type: String, required: true },
  },
  { collection: "auth_states" }
);
AuthStateSchema.index({ accountId: 1, type: 1 }, { unique: true });

// ─── Saved account info (phone numbers, reconnect on restart) ─────────
const AccountInfoSchema = new Schema(
  {
    accountIndex: { type: Number, required: true, unique: true },
    phoneNumber: { type: String, default: "" },
    hasAuth: { type: Boolean, default: false },
  },
  { collection: "account_infos" }
);

// ─── Active broadcast (persisted for restart resume) ───────────────────
const GroupSchema = new Schema({ id: String, name: String }, { _id: false });
const AccountSelectionSchema = new Schema(
  {
    accountIndex: Number,
    groupIds: [String],
    groups: [GroupSchema],
  },
  { _id: false }
);

const ActiveBroadcastSchema = new Schema(
  {
    userId: { type: Number, required: true, unique: true },
    chatId: { type: Number, required: true },
    active: { type: Boolean, default: false },
    broadcastEndTime: { type: Number, default: null },
    broadcastCycles: { type: Number, default: 0 },
    repeatHours: { type: Number, default: 1 },
    delaySeconds: { type: Number, default: 5 },
    conversationMode: { type: Boolean, default: true },
    accountSelections: [AccountSelectionSchema],
  },
  { collection: "active_broadcasts" }
);

const AuthState = mongoose.model("AuthState", AuthStateSchema);
const AccountInfo = mongoose.model("AccountInfo", AccountInfoSchema);
const ActiveBroadcast = mongoose.model("ActiveBroadcast", ActiveBroadcastSchema);

module.exports = { AuthState, AccountInfo, ActiveBroadcast };

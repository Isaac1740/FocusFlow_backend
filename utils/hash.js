import crypto from "crypto";

export function hashIdentifier(value) {
  return crypto
    .createHash("sha256")
    .update(value.toLowerCase())
    .digest("hex");
}

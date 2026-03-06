export const getSignerPrimaryAction = (hasCredential) => (hasCredential ? "Sign with passkey" : "Set up passkey to sign");

export const getPasskeyEnvironmentMessage = ({ supported, secure }) => {
  if (!supported) return "Passkeys are not supported in this browser. Use another browser or device.";
  if (!secure) return "Passkeys require a secure connection (HTTPS).";
  return "";
};

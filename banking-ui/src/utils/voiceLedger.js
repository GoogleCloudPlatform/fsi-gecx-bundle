export function formatVoiceLedgerAmount(amountCents) {
  const numericAmount = Number(amountCents);
  const safeAmount = Number.isFinite(numericAmount) ? numericAmount : 0;
  return `$${Math.abs(safeAmount / 100).toFixed(2)}`;
}

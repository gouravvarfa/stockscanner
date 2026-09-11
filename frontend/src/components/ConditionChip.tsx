export function ConditionChip({ label, passed }: { label: string; passed: boolean }) {
  return (
    <span className={passed ? "chip chip-pass" : "chip chip-fail"}>
      {passed ? "✓" : "✗"} {label.replace(/_/g, " ")}
    </span>
  );
}

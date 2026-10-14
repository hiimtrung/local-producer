// An inline "are you sure" with a cancel and a destructive confirm.
import { Button } from "../atoms";

export interface ConfirmBarProps {
  question: string;
  confirm: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmBar({ question, confirm, onConfirm, onCancel }: ConfirmBarProps) {
  return (
    <div className="confirm" role="alertdialog" aria-label={question}>
      <span className="callout">{question}</span>
      <Button size="sm" variant="plain" onClick={onCancel}>
        Keep
      </Button>
      <Button size="sm" variant="destructive" onClick={onConfirm}>
        {confirm}
      </Button>
    </div>
  );
}

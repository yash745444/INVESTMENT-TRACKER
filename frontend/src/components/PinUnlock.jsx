import { useEffect, useState } from "react";
import { api, apiError } from "../lib/api";
import { setSharesUnlocked } from "../lib/sharesLock";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "./ui/dialog";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "./ui/input-otp";
import { Lock } from "lucide-react";

export function PinUnlock({ open, onOpenChange, onUnlock }) {
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) { setPin(""); setError(""); }
  }, [open]);

  useEffect(() => {
    if (pin.length !== 4 || busy) return;
    setBusy(true);
    api.post("/shares/unlock", { pin })
      .then(() => { setSharesUnlocked(); onUnlock(); onOpenChange(false); })
      .catch((e) => { setError(apiError(e)); setPin(""); })
      .finally(() => setBusy(false));
  }, [pin]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xs" data-testid="pin-dialog">
        <DialogHeader>
          <DialogTitle className="font-heading flex items-center gap-2">
            <Lock className="h-4 w-4" /> Shares Passcode
          </DialogTitle>
          <DialogDescription>Enter your 4-digit passcode to reveal share holdings</DialogDescription>
        </DialogHeader>
        <div className="flex justify-center py-2">
          <InputOTP maxLength={4} value={pin} onChange={setPin} data-testid="pin-input">
            <InputOTPGroup>
              <InputOTPSlot index={0} />
              <InputOTPSlot index={1} />
              <InputOTPSlot index={2} />
              <InputOTPSlot index={3} />
            </InputOTPGroup>
          </InputOTP>
        </div>
        {error && <p className="text-sm text-negative text-center" data-testid="pin-error">{error}</p>}
      </DialogContent>
    </Dialog>
  );
}

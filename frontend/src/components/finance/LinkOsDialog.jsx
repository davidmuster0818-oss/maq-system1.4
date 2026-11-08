import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { api, errMsg } from "@/components/finance/api";
import { OsPicker } from "@/components/finance/TxForm";
import { toast } from "sonner";

export default function LinkOsDialog({ tx, onClose, onSaved }) {
  const [ids, setIds] = useState([]);

  useEffect(() => {
    setIds(tx?.os_ids || []);
  }, [tx]);

  const save = async () => {
    try {
      await api.put(`/finance/transactions/${tx.id}/links`, { os_ids: ids });
      toast.success(ids.length ? "Vínculos atualizados" : "Lançamento desvinculado");
      onSaved();
      onClose();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  return (
    <Dialog open={!!tx} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-white max-w-md" data-testid="link-os-dialog">
        <DialogHeader><DialogTitle>Vincular a Ordens de Serviço</DialogTitle></DialogHeader>
        <p className="text-sm text-slate-500">{tx?.description}. Com várias OSs, o valor é dividido igualmente entre elas.</p>
        <OsPicker value={ids} onChange={setIds} testPrefix="link-os" />
        <DialogFooter>
          <Button variant="outline" onClick={() => setIds([])} data-testid="link-os-clear-btn">Desvincular todas</Button>
          <Button className="bg-blue-600 hover:bg-blue-700" onClick={save} data-testid="link-os-save-btn">Salvar vínculos</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

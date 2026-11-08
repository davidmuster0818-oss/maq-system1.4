import React from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Button } from '../components/ui/button';
import { Printer, FileCheck } from 'lucide-react';

const SignatureViewModal = ({ open, onClose, sigData }) => {
  if (!sigData || !sigData.signed) return null;

  const order = sigData.order_summary || {};
  const sigDate = sigData.signature_date
    ? new Date(sigData.signature_date).toLocaleString('pt-BR')
    : '';

  const handlePrint = () => {
    window.print();
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="signature-view-modal" data-overlay="true">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileCheck className="h-5 w-5 text-green-600" />
            Assinaturas - OS {order.os_number}
          </DialogTitle>
        </DialogHeader>

        {/* Printable content */}
        <div id="signature-print-area" className="space-y-6">
          {/* Copy header */}
          <div className="border border-gray-200 rounded-lg p-4 bg-gray-50">
            <h3 className="text-base font-semibold text-gray-800 mb-3">Dados da Ordem de Servico</h3>
            <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
              <div><span className="font-medium text-gray-600">OS:</span> <span className="text-gray-900">{order.os_number}</span></div>
              <div><span className="font-medium text-gray-600">Data:</span> <span className="text-gray-900">{order.registration_date}</span></div>
              <div><span className="font-medium text-gray-600">Cliente:</span> <span className="text-gray-900">{order.customer_name}</span></div>
              <div><span className="font-medium text-gray-600">Tecnico:</span> <span className="text-gray-900">{order.technician}</span></div>
              <div><span className="font-medium text-gray-600">Produto:</span> <span className="text-gray-900">{order.product} {order.brand}</span></div>
              <div><span className="font-medium text-gray-600">Modelo:</span> <span className="text-gray-900">{order.model}</span></div>
              <div><span className="font-medium text-gray-600">Tipo:</span> <span className="text-gray-900">{order.service_type}</span></div>
              <div><span className="font-medium text-gray-600">Status:</span> <span className="text-gray-900">{order.status}</span></div>
              <div className="col-span-2"><span className="font-medium text-gray-600">Defeito:</span> <span className="text-gray-900">{order.reported_defect}</span></div>
              {order.technical_diagnosis && (
                <div className="col-span-2"><span className="font-medium text-gray-600">Diagnostico:</span> <span className="text-gray-900">{order.technical_diagnosis}</span></div>
              )}
            </div>
          </div>

          {/* Signatures */}
          <div className="border border-gray-200 rounded-lg p-4">
            <h3 className="text-base font-semibold text-gray-800 mb-4">Assinaturas Digitais</h3>
            <p className="text-xs text-gray-500 mb-4">Assinado em: {sigDate}</p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              {/* Technician signature */}
              <div className="flex flex-col items-center">
                <div className="border border-gray-200 rounded-md bg-white p-2 w-full">
                  {sigData.signature_technician && (
                    <img
                      src={sigData.signature_technician}
                      alt="Assinatura Tecnico"
                      className="w-full h-24 object-contain"
                      data-testid="view-sig-tech"
                    />
                  )}
                </div>
                <div className="w-full border-t-2 border-gray-800 mt-2 pt-1">
                  <p className="text-sm font-medium text-center text-gray-700">{order.technician || 'Tecnico'}</p>
                  <p className="text-xs text-center text-gray-400">Tecnico Responsavel</p>
                </div>
              </div>

              {/* Client signature */}
              <div className="flex flex-col items-center">
                <div className="border border-gray-200 rounded-md bg-white p-2 w-full">
                  {sigData.signature_client && (
                    <img
                      src={sigData.signature_client}
                      alt="Assinatura Cliente"
                      className="w-full h-24 object-contain"
                      data-testid="view-sig-client"
                    />
                  )}
                </div>
                <div className="w-full border-t-2 border-gray-800 mt-2 pt-1">
                  <p className="text-sm font-medium text-center text-gray-700">{order.customer_name || 'Cliente'}</p>
                  <p className="text-xs text-center text-gray-400">Cliente</p>
                </div>
              </div>
            </div>
          </div>

          {/* Assinafy status */}
          {sigData.assinafy_document_id && (
            <div className="flex items-center gap-2 text-xs text-gray-400 border-t border-gray-100 pt-2">
              <FileCheck className="h-3 w-3" />
              <span>Certificado Assinafy: {sigData.assinafy_document_id}</span>
              {sigData.assinafy_status && <span>({sigData.assinafy_status})</span>}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 mt-4 print:hidden">
          <Button variant="outline" onClick={onClose} data-testid="sig-view-close-btn">Fechar</Button>
          <Button onClick={handlePrint} className="bg-blue-600 hover:bg-blue-700" data-testid="sig-view-print-btn">
            <Printer className="h-4 w-4 mr-1" /> Imprimir
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default SignatureViewModal;

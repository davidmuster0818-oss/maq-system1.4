import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { OrderDetailModal } from '../pages/ServiceOrdersPage';
import LaudoModal from '../components/LaudoModal';
import { printOS } from '../utils/printUtils';
import { sendWhatsAppCopy } from '../utils/printUtils';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;

const OrderDetailOverlay = ({ open, onClose, osNumber, onOrderUpdated }) => {
  const { getAuthHeader } = useAuth();
  const [order, setOrder] = useState(null);
  const [laudoOpen, setLaudoOpen] = useState(false);
  const [laudoOrder, setLaudoOrder] = useState(null);

  useEffect(() => {
    if (open && osNumber) {
      axios.get(`${API}/service-orders/${encodeURIComponent(osNumber)}?include_photos=1`, getAuthHeader())
        .then(res => setOrder(res.data))
        .catch(() => toast.error(`OS ${osNumber} não encontrada`));
    }
    if (!open) {
      setOrder(null);
      setLaudoOpen(false);
      setLaudoOrder(null);
    }
  }, [open, osNumber, getAuthHeader]);

  const handleUpdate = useCallback(async (updatedOrder) => {
    try {
      await axios.put(`${API}/service-orders/${encodeURIComponent(updatedOrder.os_number)}`, updatedOrder, getAuthHeader());
      setOrder(updatedOrder);
      toast.success('OS atualizada');
      if (onOrderUpdated) onOrderUpdated();
    } catch {
      toast.error('Erro ao salvar OS');
    }
  }, [getAuthHeader, onOrderUpdated]);

  const handleWhatsApp = useCallback((phone) => {
    if (!phone) return;
    const num = phone.replace(/\D/g, '');
    const wa = num.startsWith('55') ? num : `55${num}`;
    window.open(`https://wa.me/${wa}`, '_blank');
  }, []);

  const handleMaps = useCallback((o) => {
    if (o.lat && o.lng) {
      window.open(`https://www.google.com/maps?q=${o.lat},${o.lng}`, '_blank');
    } else {
      const addr = `${o.address || ''} ${o.number || ''}, ${o.neighborhood || ''} - ${o.city || ''}, ${o.state || ''}`;
      window.open(`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(addr)}`, '_blank');
    }
  }, []);

  const handleTelecontrol = useCallback((osNum) => {
    window.open(`https://posvenda.telecontrol.com.br/assist/os_press.php?os=${osNum}`, '_blank');
  }, []);

  const handlePrint = useCallback((o, sigData) => {
    printOS(o, sigData);
  }, []);

  const handleSendWhatsAppCopy = useCallback(async (o, sigData) => {
    await sendWhatsAppCopy(o, sigData, toast);
  }, []);

  const handleOpenLaudo = useCallback((o) => {
    setLaudoOrder(o);
    setLaudoOpen(true);
  }, []);

  if (!order) return null;

  return (
    <>
      <OrderDetailModal
        open={open}
        onClose={onClose}
        order={order}
        onUpdate={handleUpdate}
        onWhatsApp={handleWhatsApp}
        onMaps={handleMaps}
        onTelecontrol={handleTelecontrol}
        onPrint={handlePrint}
        onSendWhatsAppCopy={handleSendWhatsAppCopy}
        onOpenLaudo={handleOpenLaudo}
        isOverlay={true}
      />
      {laudoOrder && (
        <LaudoModal
          open={laudoOpen}
          onClose={() => { setLaudoOpen(false); setLaudoOrder(null); }}
          order={laudoOrder}
          getAuthHeader={getAuthHeader}
        />
      )}
    </>
  );
};

export default OrderDetailOverlay;

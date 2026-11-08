import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { LayoutDashboard, ArrowDownToLine, ArrowUpFromLine, Tags, Repeat, Target, Users, Landmark, Bot, Lock, Loader2 } from 'lucide-react';
import DashboardLayout from '../components/DashboardLayout';
import { api } from '../components/finance/api';
import { RefDataProvider } from '../components/finance/RefData';
import Overview from '../components/finance/Overview';
import Transactions from '../components/finance/Transactions';
import Categories from '../components/finance/Categories';
import Recurring from '../components/finance/Recurring';
import Budgets from '../components/finance/Budgets';
import Technicians from '../components/finance/Technicians';
import Banks from '../components/finance/Banks';
import Assistants from '../components/finance/Assistants';

const TABS = [
  { id: 'visao-geral', label: 'Visão Geral', Icon: LayoutDashboard, tech: true, el: () => <Overview /> },
  { id: 'entradas', label: 'Entradas', Icon: ArrowDownToLine, tech: true, el: () => <Transactions type="entrada" /> },
  { id: 'saidas', label: 'Saídas', Icon: ArrowUpFromLine, tech: true, el: () => <Transactions type="saida" /> },
  { id: 'categorias', label: 'Categorias', Icon: Tags, el: () => <Categories /> },
  { id: 'despesas-fixas', label: 'Despesas Fixas', Icon: Repeat, el: () => <Recurring /> },
  { id: 'metas-limites', label: 'Metas e Limites', Icon: Target, el: () => <Budgets /> },
  { id: 'tecnicos', label: 'Técnicos', Icon: Users, tech: true, el: () => <Technicians /> },
  { id: 'bancos', label: 'Bancos', Icon: Landmark, el: () => <Banks /> },
  { id: 'assistentes', label: 'Assistentes', Icon: Bot, el: () => <Assistants /> },
];

function Blocked() {
  return (
    <div className="max-w-xl mx-auto mt-20 p-8 text-center border border-slate-200 rounded-xl bg-white" data-testid="finance-blocked">
      <Lock className="mx-auto text-slate-400 mb-3" />
      <h1 className="text-xl font-semibold text-slate-900">Sem acesso ao Financeiro</h1>
      <p className="text-sm text-slate-500 mt-2">O seu cadastro não libera esta página. Fale com o administrador.</p>
    </div>
  );
}

export default function FinancialPage() {
  const { tab = 'visao-geral' } = useParams();
  const navigate = useNavigate();
  const [me, setMe] = useState(null);

  useEffect(() => {
    api.get('/finance/me').then((r) => setMe(r.data)).catch(() => setMe({ has_finance: false }));
  }, []);

  if (!me) return <DashboardLayout><div className="py-20 text-center text-slate-500"><Loader2 className="h-5 w-5 animate-spin inline mr-2" />Carregando…</div></DashboardLayout>;
  if (!me.has_finance) return <DashboardLayout><Blocked /></DashboardLayout>;

  const tabs = TABS.filter((t) => me.is_admin || t.tech);
  const current = tabs.find((t) => t.id === tab) || tabs[0];

  return (
    <DashboardLayout>
      <RefDataProvider>
        <div className="space-y-6 text-slate-900" data-testid="financial-page">
          <div className="border-b border-slate-200">
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">Financeiro</h1>
            <p className="text-sm text-slate-500 mt-1">Quanto entrou, quanto saiu, quanto cada OS rendeu e quanto falta receber.</p>
            <div className="flex gap-1 mt-4 overflow-x-auto -mb-px" data-testid="finance-tabs">
              {tabs.map(({ id, label, Icon }) => (
                <button key={id} onClick={() => navigate(`/financial/${id}`)} data-testid={`tab-nav-${id}`}
                  className={`flex items-center gap-2 px-3 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${current.id === id ? 'border-blue-600 text-blue-700' : 'border-transparent text-slate-500 hover:text-slate-900'}`}>
                  <Icon size={15} />{label}
                </button>
              ))}
            </div>
          </div>
          <div className="space-y-6 fade-up" key={current.id}>
            {current.el()}
          </div>
        </div>
      </RefDataProvider>
    </DashboardLayout>
  );
}

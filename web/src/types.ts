// Mirrors the FastAPI response shapes (the OpenAPI contract).

export type AccountKind = "personal" | "joint";
export type MovementType = "income" | "expense" | "transfer" | "capital" | "drawing";
export type Role = "owner" | "partner" | "staff";
export type PeriodStatus = "open" | "closed";

export interface Me { user_id: number; email: string; clinic_id: number; role: Role; }
export interface Partner { id: number; name: string; }

// A member of the clinic's allowlist (ADR-0008). "pending" until the invitee
// first signs in; `id` is the Membership id (the thing you revoke).
export type MemberStatus = "active" | "pending";
export interface Member {
  id: number; user_id: number; email: string;
  full_name: string | null; role: Role; status: MemberStatus;
}
export interface InviteResult {
  member: Member;
  status: "invited" | "reactivated" | "already_member";
}
export interface Account {
  id: number; name: string; kind: AccountKind;
  owner_partner_id: number | null; opening_balance: number; is_active: boolean;
}
export interface Category { id: number; name: string; }
export interface Procedure { id: number; name: string; default_price: number; }
export interface Employee { id: number; name: string; role: string | null; salary: number; }

export interface Patient { id: number; name: string; phone: string | null; notes: string | null; }
export interface Case {
  id: number; patient_id: number; procedure_name: string;
  agreed_price: number; status: string; outstanding: number;
}
export interface PatientDetail extends Patient { total_outstanding: number; cases: Case[]; }

export interface Movement {
  id: number; type: MovementType; amount: number; date: string;
  partner_id: number | null; from_account_id: number | null; to_account_id: number | null;
  case_id: number | null; note: string | null;
}

export interface Period {
  id: number; start_date: string; end_date: string; status: PeriodStatus;
}
export interface SettlementBalance { partner_id: number; personal_profit: number; settlement_balance: number; }
export interface SettlementObligation {
  id: number; from_partner_id: number; to_partner_id: number; amount: number; paid: boolean;
}
export interface SettlementStatement {
  id: number; period_id: number; profit: number; joint_standing: number;
  balances: SettlementBalance[]; obligations: SettlementObligation[];
}

export interface AccountBalance { account_id: number; name: string; balance: number; }
export interface DashboardSummary {
  period_id: number | null; income: number; expense: number; net_profit: number;
  account_balances: AccountBalance[];
}

export interface CategoryTotal { category_id: number | null; name: string; total: number; }
export interface ProcedureStat { procedure_name: string; count: number; revenue: number; }
export interface CollectorTotal { partner_id: number; name: string; collected: number; }
export interface ReceivableRow { patient_id: number; name: string; outstanding: number; }
export interface Receivables { total: number; rows: ReceivableRow[]; }
export interface TrendPoint { month: string; income: number; expense: number; net_profit: number; }
export interface PartnerContribution {
  partner_id: number; name: string; collected: number; paid: number; entitled: number;
}
export interface Reminder {
  kind: string; severity: string; message: string;
  entity_type: string | null; entity_id: number | null;
}
export interface AuditLog {
  id: number; user_id: number | null; action: string;
  entity_type: string; entity_id: number | null; at: string;
}

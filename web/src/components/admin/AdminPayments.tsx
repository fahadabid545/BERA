"use client";

import { useCallback, useEffect, useState } from "react";

import { Button, Input, Select, Table, Tag, TextLink, type TagVariant } from "@/components/ui";
import { getJson, type ApiError } from "@/lib/api";

type Kind = "payment" | "refund" | "failure";
type PaymentItem = {
  id: string;
  provider_event_id: string;
  kind: Kind;
  company_id: number;
  company: string;
  amount: string;
  currency: string;
  reason: string;
  at: string;
};
type Total = {
  currency: string;
  payments: { count: number; amount: string };
  refunds: { count: number; amount: string };
  failures: { count: number };
};
type Overview = {
  total: number;
  page: number;
  page_size: number;
  totals: Total[];
  items: PaymentItem[];
  companies: { id: number; name: string }[];
  currencies: string[];
};

const BASE = "/api/admin/payments/";
const ALL = "";
const DATE_LENGTH = 10;
const KIND_WORDS: Record<Kind, string> = {
  payment: "Payment",
  refund: "Refund",
  failure: "Failure",
};
const KIND_TAGS: Record<Kind, TagVariant> = {
  payment: "success",
  refund: "neutral",
  failure: "danger",
};
const KINDS = Object.keys(KIND_WORDS) as Kind[];

/** Payments, refunds and failed payments as the payment provider reported them, with filters and
 * a link to each company. Amounts of different currencies are never added together. */
export function AdminPayments() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [filters, setFilters] = useState({
    kind: ALL,
    company: ALL,
    currency: ALL,
    from_date: "",
    to_date: "",
  });
  const [page, setPage] = useState(1);
  const [error, setError] = useState<ApiError | null>(null);

  const load = useCallback(async () => {
    const query = new URLSearchParams();
    for (const [name, value] of Object.entries(filters)) if (value) query.set(name, value);
    if (page > 1) query.set("page", String(page));
    const result = await getJson<Overview>(`${BASE}?${query}`);
    if (result.ok) {
      setOverview(result.data);
      setError(null);
    } else setError(result.error);
  }, [filters, page]);

  useEffect(() => {
    void load();
  }, [load]);

  const change = (name: keyof typeof filters) => (event: { target: { value: string } }) => {
    setFilters({ ...filters, [name]: event.target.value });
    setPage(1);
  };

  if (!overview) {
    return error ? (
      <p className="ui-error" role="alert">
        {error.message}
      </p>
    ) : null;
  }
  const lastPage = Math.max(1, Math.ceil(overview.total / overview.page_size));
  return (
    <div className="page-stack">
      {error && (
        <p className="ui-error" role="alert">
          {error.message}
        </p>
      )}
      <div className="page-actions">
        <Select
          label="Type"
          value={filters.kind}
          onChange={change("kind")}
          options={[
            { value: ALL, label: "All types" },
            ...KINDS.map((kind) => ({ value: kind, label: KIND_WORDS[kind] })),
          ]}
        />
        <Select
          label="Company"
          value={filters.company}
          onChange={change("company")}
          options={[
            { value: ALL, label: "All companies" },
            ...overview.companies.map((entry) => ({ value: String(entry.id), label: entry.name })),
          ]}
        />
        <Select
          label="Currency"
          value={filters.currency}
          onChange={change("currency")}
          options={[
            { value: ALL, label: "All currencies" },
            ...overview.currencies.map((code) => ({ value: code, label: code })),
          ]}
        />
        <Input label="From" type="date" value={filters.from_date} onChange={change("from_date")} />
        <Input label="To" type="date" value={filters.to_date} onChange={change("to_date")} />
      </div>
      <Table label="Totals">
        <thead>
          <tr>
            <th scope="col">Currency</th>
            <th scope="col">Payments</th>
            <th scope="col">Refunds</th>
            <th scope="col">Failures</th>
          </tr>
        </thead>
        <tbody>
          {overview.totals.map((entry) => (
            <tr key={entry.currency}>
              <th scope="row">{entry.currency}</th>
              <td>{`${entry.payments.count} (${entry.payments.amount})`}</td>
              <td>{`${entry.refunds.count} (${entry.refunds.amount})`}</td>
              <td>{entry.failures.count}</td>
            </tr>
          ))}
        </tbody>
      </Table>
      {overview.items.length === 0 ? (
        <p role="status">No payments.</p>
      ) : (
        <Table label="Payments">
          <thead>
            <tr>
              <th scope="col">Date</th>
              <th scope="col">Company</th>
              <th scope="col">Type</th>
              <th scope="col">Amount</th>
              <th scope="col">Reason</th>
              <th scope="col">Provider event</th>
            </tr>
          </thead>
          <tbody>
            {overview.items.map((item) => (
              <tr key={item.id}>
                <td>{item.at.slice(0, DATE_LENGTH)}</td>
                <td>
                  <TextLink href={`/admin/companies/${item.company_id}`}>{item.company}</TextLink>
                </td>
                <td>
                  <Tag variant={KIND_TAGS[item.kind]}>{KIND_WORDS[item.kind]}</Tag>
                </td>
                <td>{`${item.amount} ${item.currency}`}</td>
                <td>{item.reason}</td>
                <td>{item.provider_event_id}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      <div className="pager">
        <Button variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
          Previous
        </Button>
        <span role="status">{`Page ${overview.page} of ${lastPage}`}</span>
        <Button variant="secondary" disabled={page >= lastPage} onClick={() => setPage(page + 1)}>
          Next
        </Button>
      </div>
    </div>
  );
}

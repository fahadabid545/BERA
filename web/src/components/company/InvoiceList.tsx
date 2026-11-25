"use client";

import { useEffect, useState } from "react";

import { useCompanyRole } from "@/components/company/role";
import { Button, Table } from "@/components/ui";
import { getJson } from "@/lib/api";
import { navigateTo } from "@/lib/navigation";

const INVOICES_URL = "/api/company/billing/invoices/";
const USAGE_URL = "/api/company/usage/";

type Invoice = {
  id: string;
  number: string;
  issued_at: string;
  amount_minor: number;
  currency: string;
  plan_name: string | null;
  billed_to_name: string;
  can_download: boolean;
  can_view: boolean;
};

const date = (iso: string) =>
  new Date(iso).toLocaleDateString("en-US", { dateStyle: "medium", timeZone: "UTC" });
const amount = (invoice: Invoice) =>
  `${invoice.currency} ${(invoice.amount_minor / 100).toLocaleString("en-US", {
    minimumFractionDigits: 2,
  })}`;

/** The invoices the payment provider issued, newest first. The provider's links are asked for
 * one at a time, only when the owner clicks. */
export function InvoiceList() {
  const isOwner = useCompanyRole() === "owner";
  const [invoices, setInvoices] = useState<Invoice[] | null>(null);
  const [free, setFree] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [opening, setOpening] = useState(false);

  useEffect(() => {
    if (!isOwner) return;
    void getJson<{ invoices: Invoice[] }>(INVOICES_URL).then((result) => {
      if (result.ok) setInvoices(result.data.invoices);
      else setProblem(result.error.message);
    });
    void getJson<{ state: string }>(USAGE_URL).then((result) => {
      if (result.ok) setFree(result.data.state === "granted_free");
    });
  }, [isOwner]);

  if (!isOwner) return null;

  async function open(invoice: Invoice, kind: "pdf" | "hosted") {
    if (opening) return;
    setOpening(true);
    setProblem(null);
    const result = await getJson<{ url: string }>(
      `${INVOICES_URL}${invoice.id}/link/?kind=${kind}`,
    );
    setOpening(false);
    if (result.ok) navigateTo(result.data.url);
    else setProblem(result.error.message);
  }

  return (
    <div className="page-stack">
      <h2>Invoices</h2>
      {problem && <p role="alert">{problem}</p>}
      {invoices && invoices.length === 0 && (
        <p>{free ? "A free plan has no invoices." : "No invoices yet."}</p>
      )}
      {invoices && invoices.length > 0 && (
        <Table label="Invoices">
          <thead>
            <tr>
              <th scope="col">Number</th>
              <th scope="col">Date</th>
              <th scope="col">Plan</th>
              <th scope="col">Billed to</th>
              <th scope="col">Amount</th>
              <th scope="col">
                <span className="visually-hidden">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {invoices.map((invoice) => (
              <tr key={invoice.id}>
                <th scope="row">{invoice.number || "Pending"}</th>
                <td>{date(invoice.issued_at)}</td>
                <td>{invoice.plan_name ?? ""}</td>
                <td>{invoice.billed_to_name}</td>
                <td>{amount(invoice)}</td>
                <td>
                  <Button
                    variant="secondary"
                    disabled={!invoice.can_download || opening}
                    aria-label={`Download invoice ${invoice.number}`}
                    onClick={() => void open(invoice, "pdf")}
                  >
                    Download
                  </Button>{" "}
                  <Button
                    variant="secondary"
                    disabled={!invoice.can_view || opening}
                    aria-label={`View invoice ${invoice.number}`}
                    onClick={() => void open(invoice, "hosted")}
                  >
                    View
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  );
}

import { notFound } from "next/navigation";

import {
  Button,
  ButtonLink,
  Card,
  Checkbox,
  Input,
  Menu,
  Select,
  Textarea,
  TextLink,
  Table,
  TabLinks,
  Tabs,
  Tag,
  ThemeToggle,
  ToggleIcon,
  Tooltip,
} from "@/components/ui";

import { ChartCard } from "@/components/charts/ChartCard";
import { Coverage } from "@/components/charts/Coverage";
import { Funnel } from "@/components/charts/Funnel";
import { Histogram } from "@/components/charts/Histogram";
import { Ranking } from "@/components/charts/Ranking";
import { Trend } from "@/components/charts/Trend";
import { RenewalPrompt, UpgradePrompt } from "@/components/company/BillingPrompt";

import { ComparisonSample } from "./ComparisonSample";
import { DashboardSample } from "./DashboardSample";
import { DeleteConfirmation } from "./DeleteConfirmation";

export const metadata = { title: "BERA design sample" };

/** Shows every building block. Only for development; hidden in production builds. */
export default function DesignSample() {
  if (process.env.NODE_ENV === "production") notFound();

  return (
    <main className="sample-page">
      <h1>Design foundation</h1>
      <ThemeToggle />

      <section className="sample-section" aria-labelledby="sample-type">
        <h2 id="sample-type">Type and colour</h2>
        <h3>Heading</h3>
        <p>Body</p>
        <p className="mono">REF A1B2C3D4 · 1,284.50</p>
      </section>

      <section className="sample-section" aria-labelledby="sample-buttons">
        <h2 id="sample-buttons">Buttons</h2>
        <div className="sample-row">
          <Button>Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="danger">Delete</Button>
          <Button disabled>Disabled</Button>
          <ButtonLink href="/pricing" variant="secondary">
            Link styled as button
          </ButtonLink>
          <TextLink href="/pricing">Text link</TextLink>
        </div>
      </section>

      <section className="sample-section" aria-labelledby="sample-inputs">
        <h2 id="sample-inputs">Inputs, selects and checkboxes</h2>
        <div className="sample-grid">
          <Input label="Project name" placeholder="Senior welder" />
          <Input
            label="Email"
            type="email"
            defaultValue="not-an-email"
            error="Enter a valid email address."
          />
          <Textarea label="Notes" placeholder="Anything to add" />
          <Select
            label="Keep CVs for"
            options={[
              { value: "30", label: "30 days" },
              { value: "180", label: "180 days" },
            ]}
            defaultValue="180"
          />
          <div>
            <Checkbox label="Notify me when screening finishes" defaultChecked />
            <Checkbox label="Share a summary with my team" />
          </div>
        </div>
      </section>

      <section className="sample-section" aria-labelledby="sample-charts">
        <h2 id="sample-charts">Charts</h2>
        <div className="chart-grid">
          <ChartCard title="Funnel">
            <Funnel
              steps={[
                { step: "uploaded", count: 40 },
                { step: "read", count: 36 },
                { step: "scored", count: 30 },
                { step: "shortlisted", count: 12 },
                { step: "interview", count: 6 },
                { step: "approved", count: 2 },
              ]}
            />
          </ChartCard>
          <ChartCard title="Score distribution">
            <Histogram
              grades={[
                { grade: "A", count: 3 },
                { grade: "B", count: 9 },
                { grade: "C", count: 12 },
                { grade: "D", count: 5 },
                { grade: "E", count: 1 },
              ]}
            />
          </ChartCard>
          <ChartCard title="Ranking">
            <Ranking
              projectId="sample"
              candidates={[
                {
                  rank: 1,
                  candidate_id: "a",
                  file_name: "a.pdf",
                  name: "A. B.",
                  score: "91.5",
                  grade: "A",
                },
                {
                  rank: 2,
                  candidate_id: "b",
                  file_name: "b.pdf",
                  name: "C. D.",
                  score: "78.0",
                  grade: "C",
                },
              ]}
            />
          </ChartCard>
          <ChartCard title="Requirement coverage">
            <Coverage
              candidates={10}
              requirements={[
                {
                  requirement_id: "r",
                  text: "Python",
                  kind: "must",
                  met: 5,
                  partly_met: 2,
                  missing: 2,
                  not_judged: 1,
                },
              ]}
            />
          </ChartCard>
          <div className="chart-grid__wide">
            <ChartCard title="Trend">
              <Trend
                metric={{
                  current: [1, 3, 2, 5, 4, 6, 8],
                  previous: [2, 2, 3, 3, 2, 4, 3],
                  total: 29,
                  previous_total: 19,
                  change_percent: 52.6,
                }}
                start="2026-11-01"
                label="CVs uploaded"
              />
            </ChartCard>
          </div>
        </div>
      </section>

      <section className="sample-section" aria-labelledby="sample-dashboard">
        <h2 id="sample-dashboard">Dashboard</h2>
        <DashboardSample />
      </section>

      <section className="sample-section" aria-labelledby="sample-comparison">
        <h2 id="sample-comparison">Comparison</h2>
        <ComparisonSample />
      </section>

      <section className="sample-section" aria-labelledby="sample-cards">
        <h2 id="sample-cards">Cards, tags and tooltips</h2>
        <div className="sample-grid">
          <Card>
            <h3>Normal card</h3>
          </Card>
          <Card selected>
            <h3>Selected card</h3>
          </Card>
        </div>
        <div className="sample-row" style={{ marginTop: "var(--space-4)" }}>
          <Tag>Neutral</Tag>
          <Tag variant="success">Strong match</Tag>
          <Tag variant="warning">Missing must-have</Tag>
          <Tag variant="danger">Not recommended</Tag>
          <Tag variant="live">Live</Tag>
          <Tag variant="admin">Admin</Tag>
          <Tooltip content="Tooltip">
            <Button variant="secondary">Hover or focus me</Button>
          </Tooltip>
        </div>
      </section>

      <section className="sample-section" aria-labelledby="sample-table">
        <h2 id="sample-table">Table</h2>
        <Table label="Sample candidates">
          <thead>
            <tr>
              <th scope="col">Candidate</th>
              <th scope="col">Score</th>
              <th scope="col">Result</th>
            </tr>
          </thead>
          <tbody>
            <tr data-selected="true">
              <td>Candidate 1042</td>
              <td className="mono">88</td>
              <td>
                <Tag variant="success">Strong match</Tag>
              </td>
            </tr>
            <tr>
              <td>Candidate 1043</td>
              <td className="mono">61</td>
              <td>
                <Tag variant="warning">Possible</Tag>
              </td>
            </tr>
          </tbody>
        </Table>
      </section>

      <section className="sample-section" aria-labelledby="sample-icons">
        <h2 id="sample-icons">Icon items</h2>
        <div className="sample-row">
          <span className="ui-icon-item">
            <ToggleIcon name="features" />
            Idle
          </span>
          <span className="ui-icon-item" data-active="true">
            <ToggleIcon name="pricing" />
            Current
          </span>
          <span className="ui-icon-item">
            <ToggleIcon name="faq" />
            Idle
          </span>
          <span className="ui-icon-item" data-active="true">
            <ToggleIcon name="contact" />
            Current
          </span>
        </div>
      </section>

      <section className="sample-section" aria-labelledby="sample-tabs">
        <h2 id="sample-tabs">Tabs and popup</h2>
        <Tabs
          label="Sample sections"
          tabs={[
            { value: "overview", label: "Overview", content: <p>Overview</p> },
            { value: "details", label: "Details", content: <p>Details</p> },
            { value: "history", label: "History", content: <p>History</p> },
          ]}
        />
        <TabLinks
          label="Sample pages"
          items={[
            { label: "Design", href: "/design", exact: true },
            { label: "Pricing", href: "/pricing" },
          ]}
        />
        <DeleteConfirmation />
        <UpgradePrompt trigger={<Button variant="secondary">Open upgrade prompt</Button>} />
        <RenewalPrompt trigger={<Button variant="secondary">Open renewal prompt</Button>} />
        <Menu
          trigger={<Button variant="secondary">Menu</Button>}
          items={[
            { label: "Profile", href: "/company/settings/profile" },
            { label: "Log out", href: "/login" },
          ]}
        />
      </section>
    </main>
  );
}

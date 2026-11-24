"use client";

import { Table, Tag } from "@/components/ui";

import { AdminSettingsTable } from "./AdminSettingsTable";

/** Session lengths and password rules, and the status of the rule that every admin uses two-step
 * verification. That rule is always on: it is shown here and has no switch. */
export function AdminSecurity() {
  return (
    <AdminSettingsTable page="security">
      {(listing) =>
        listing.admin_two_step && (
          <Table label="Two-step verification for admins">
            <thead>
              <tr>
                <th scope="col">Requirement</th>
                <th scope="col">Admins with two-step set up</th>
                <th scope="col">Admins yet to set it up</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  <Tag variant="success">Required for every admin</Tag>
                </td>
                <td>{listing.admin_two_step.set_up}</td>
                <td>{listing.admin_two_step.not_set_up}</td>
              </tr>
            </tbody>
          </Table>
        )
      }
    </AdminSettingsTable>
  );
}

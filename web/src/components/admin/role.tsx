"use client";

import { createContext, useContext } from "react";

import type { AdminRole } from "./navigation";

const RoleContext = createContext<AdminRole>("support");

/** The signed-in admin's role. Without a provider it is the weaker one, so an action button is
 * never shown by mistake; the server refuses what a role may not do either way. */
export const AdminRoleProvider = RoleContext.Provider;
export const useAdminRole = () => useContext(RoleContext);

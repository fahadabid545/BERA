"use client";

import { createContext, useContext } from "react";

import type { CompanyRole } from "./navigation";

const RoleContext = createContext<CompanyRole>("member");

/** The signed-in person's role. Without a provider it is the weaker one, so an action button is
 * never shown by mistake; the server refuses what a role may not do either way. */
export const RoleProvider = RoleContext.Provider;
export const useCompanyRole = () => useContext(RoleContext);

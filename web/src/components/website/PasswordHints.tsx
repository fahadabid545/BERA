"use client";

import { useEffect, useRef, useState } from "react";

import { postJson } from "@/lib/api";

type Rule = { id: string; text: string; met: boolean };

const WAIT_AFTER_TYPING_MS = 400;

/**
 * The password rules, each marked met or not met for what has been typed so far. The rules
 * and their numbers come from the server (the same check that refuses a password on submit),
 * so a changed setting changes the hints. If the check cannot be reached nothing is shown:
 * the hints only help, the server still decides.
 */
export function PasswordHints({ password }: { password: string }) {
  const [rules, setRules] = useState<Rule[]>([]);
  const latest = useRef(0);

  useEffect(() => {
    const ask = ++latest.current;
    const timer = setTimeout(
      async () => {
        const result = await postJson<{ rules: Rule[] }>("/api/auth/password-check/", { password });
        if (result.ok && ask === latest.current && Array.isArray(result.data?.rules)) {
          setRules(result.data.rules);
        }
      },
      password === "" ? 0 : WAIT_AFTER_TYPING_MS,
    );
    return () => clearTimeout(timer);
  }, [password]);

  if (rules.length === 0) return null;
  return (
    <ul className="password-hints" aria-label="Password rules">
      {rules.map((rule) => (
        <li key={rule.id} className={rule.met ? "password-hints__item--met" : undefined}>
          {rule.text}: {rule.met ? "met" : "not met"}
        </li>
      ))}
    </ul>
  );
}

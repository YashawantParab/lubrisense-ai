import { redirect } from "next/navigation";

/** The product's real home screen is /overview (Phase 28) — the Phase 1
 * connectivity/status stub that used to live at "/" moved to /system. */
export default function RootPage() {
  redirect("/overview");
}

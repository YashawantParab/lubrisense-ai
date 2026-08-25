import { redirect } from "next/navigation";

/** The product's home screen is the Organization Command Center
 * (Enterprise Experience Pass A) — supersedes the former /overview redirect (Phase 28).
 * /overview itself is preserved, unlinked from primary nav, for its own fleet-asset-level
 * walkthrough content; the Phase 1 connectivity/status stub still lives at /system. */
export default function RootPage() {
  redirect("/performance/organization");
}

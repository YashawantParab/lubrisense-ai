/**
 * Server-only environment configuration.
 *
 * The `server-only` import makes this module fail to build if anything in the client
 * bundle ever imports it — that is the actual enforcement mechanism, not just a naming
 * convention. Use this for anything that must never reach the browser, and for values
 * that legitimately differ between the server and the browser (e.g. the backend's
 * internal Docker-network address, which server components use directly, versus the
 * public URL the browser uses).
 */
import "server-only";

export const serverEnv = {
  // Falls back to the public URL so server-side rendering still works if this is unset
  // (e.g. running the frontend outside Docker Compose against a locally exposed backend).
  backendInternalUrl:
    process.env.BACKEND_INTERNAL_URL ??
    process.env.NEXT_PUBLIC_API_BASE_URL ??
    "http://localhost:8000",
} as const;

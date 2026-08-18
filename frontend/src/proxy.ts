// Next.js 16 renamed `middleware.ts` -> `proxy.ts` (same mechanism, new name
// to avoid the Express.js "middleware" connotation — see the file's own
// docs at node_modules/next/dist/docs/.../proxy.md). Auth.js's `auth`
// export is just a NextRequest-in/NextResponse-out function, so it works
// unchanged under either name.
export { auth as proxy } from "@/auth";

export const config = {
  // Protect everything except the sign-in page, auth API routes, and static assets.
  matcher: ["/((?!api/auth|signin|_next/static|_next/image|favicon.ico).*)"],
};

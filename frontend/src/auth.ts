import NextAuth from "next-auth";
import Google from "next-auth/providers/google";

// Auth.js v5 + Google's OIDC provider gates the assistant behind login.
// AUTH_GOOGLE_ID / AUTH_GOOGLE_SECRET / AUTH_SECRET are read from env
// automatically by convention — see .env.example.
export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [Google],
  pages: {
    signIn: "/signin",
  },
  callbacks: {
    // Returning false here is what makes the middleware redirect
    // unauthenticated requests to the sign-in page instead of letting
    // them through.
    authorized({ auth }) {
      return !!auth?.user;
    },
  },
});

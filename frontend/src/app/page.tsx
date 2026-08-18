import { auth, signOut } from "@/auth";
import { Chat } from "@/components/Chat";

export default async function Home() {
  const session = await auth();

  return (
    <div className="flex flex-1 flex-col bg-zinc-50 dark:bg-black">
      <header className="flex items-center justify-between border-b border-gray-200 px-6 py-3 dark:border-gray-800">
        <span className="text-sm font-semibold">hybrid-rag-docs</span>
        <div className="flex items-center gap-3 text-sm text-gray-500">
          <span>{session?.user?.email}</span>
          <form
            action={async () => {
              "use server";
              await signOut({ redirectTo: "/signin" });
            }}
          >
            <button type="submit" className="underline hover:text-blue-600">
              Sign out
            </button>
          </form>
        </div>
      </header>
      <main className="flex flex-1 flex-col px-6">
        <Chat />
      </main>
    </div>
  );
}

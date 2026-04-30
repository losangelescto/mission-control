import { redirect } from "next/navigation";

// /tasks/{id} is a shareable URL surface (emails, Slack, bookmarks).
// The detail panel actually lives at /tasks?selected={id} so we
// server-redirect here. redirect() throws so the function never returns.
type TaskRedirectProps = {
  params: Promise<{ id: string }>;
};

export default async function TaskDetailRedirect({ params }: TaskRedirectProps): Promise<never> {
  const { id } = await params;
  redirect(`/tasks?selected=${encodeURIComponent(id)}`);
}

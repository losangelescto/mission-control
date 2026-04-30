import { redirect } from "next/navigation";

// The nav link is /review (singular). /reviews is a common typo we
// surface as a server redirect so users don't hit a 404.
export default function ReviewsRedirectPage(): never {
  redirect("/review");
}

import { useEffect } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "../components/shell/PageHeader";

export function NotFoundPage() {
  useEffect(() => {
    document.title = "Page not found · InfraLens";
  }, []);

  return (
    <>
      <PageHeader title="Page not found" scope="This address does not match a section of InfraLens. No data is shown for it." />
      <Link to="/" className="text-[15px] leading-6 text-ink underline">
        Go to Overview
      </Link>
    </>
  );
}

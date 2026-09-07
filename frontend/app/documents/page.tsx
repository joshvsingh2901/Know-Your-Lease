import { AuthGate } from "@/components/auth-gate";
import { DocumentLibrary } from "@/components/documents/document-library";
import { landingFontVariables } from "@/lib/fonts";

export default function DocumentsPage() {
  return (
    <main className={`landing ${landingFontVariables}`} style={{ minHeight: "100vh" }}>
      <AuthGate>
        <DocumentLibrary />
      </AuthGate>
    </main>
  );
}

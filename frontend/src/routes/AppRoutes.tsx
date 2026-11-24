import { Route, Routes } from "react-router-dom";
import { OverviewPage } from "../overview/OverviewPage";
import { ElectricityPage } from "./ElectricityPage";
import { FinancePage } from "./FinancePage";
import { NotFoundPage } from "./NotFoundPage";
import { PjmPage } from "./PjmPage";
import { ShellRoute } from "./ShellRoute";

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<ShellRoute />}>
        <Route index element={<OverviewPage />} />
        <Route path="electricity" element={<ElectricityPage />} />
        <Route path="finance" element={<FinancePage />} />
        <Route path="pjm" element={<PjmPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

import Drawer from "../../components/shared/Drawer";
import type { CAROut, QMSFindingOut } from "../../services/qms";
import FindingCaseView from "./FindingCaseView";
type Props={isOpen:boolean;amoCode:string;department:string;finding:QMSFindingOut|null;linkedCar:CAROut|null;onClose:()=>void};
export default function FindingDrawer({isOpen,amoCode,finding,linkedCar,onClose}:Props) {
  return <Drawer title="Finding review" isOpen={isOpen} onClose={onClose} panelClassName="case-finding-drawer">
    {finding?<FindingCaseView finding={finding} car={linkedCar} amoCode={amoCode}/>:<p>Select a finding.</p>}
  </Drawer>;
}

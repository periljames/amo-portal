// Components are inducted as part of the aircraft's actual configuration.
// A separate component-import workflow would bypass type-template effectivity
// and configuration conformity, so every former entry point renders the one
// universal induction cockpit.
export { default } from "./AircraftImportPage";

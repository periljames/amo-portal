# AMO Portal Route Map (Current)

## Public routes
- `/` → redirect to `/login`
- `/login`
- `/maintenance/:amoCode/login`
- `/reset-password`
- `/car-invite`

## Onboarding
- `/maintenance/:amoCode/onboarding`
- `/maintenance/:amoCode/onboarding/setup`

## Core dashboard / department landing
- `/maintenance/:amoCode` (department dashboard entry)
- `/maintenance/:amoCode/:department`

## Work orders / tasks
- `/maintenance/:amoCode/:department/work-orders`
- `/maintenance/:amoCode/:department/work-orders/:id`
- `/maintenance/:amoCode/:department/tasks/:taskId`
- `/maintenance/:amoCode/:department/tasks/:taskId/print`

## Reliability / EHM
- `/maintenance/:amoCode/ehm`
- `/maintenance/:amoCode/ehm/dashboard`
- `/maintenance/:amoCode/ehm/trends`
- `/maintenance/:amoCode/ehm/uploads`
- `/maintenance/:amoCode/reliability`
- `/maintenance/:amoCode/reliability/reports`

## Training
- `/maintenance/:amoCode/:department/training`
- `/maintenance/:amoCode/:department/qms/training`
- `/maintenance/:amoCode/:department/qms/training/:userId`

## QMS module
- `/maintenance/:amoCode/:department/qms`
- `/maintenance/:amoCode/:department/qms/tasks`
- `/maintenance/:amoCode/:department/qms/documents`
- `/maintenance/:amoCode/:department/qms/audits`
- `/maintenance/:amoCode/:department/qms/change-control`
- `/maintenance/:amoCode/:department/qms/cars`
- `/maintenance/:amoCode/:department/qms/events`
- `/maintenance/:amoCode/:department/qms/kpis`

## Aircraft / component import
- `/maintenance/:amoCode/:department/aircraft-import`
- `/maintenance/:amoCode/:department/component-import`
- `/maintenance/:amoCode/:department/aircraft-documents`

## CRS
- `/maintenance/:amoCode/:department/crs/new`

## User widgets
- `/maintenance/:amoCode/:department/settings/widgets`

## Billing / admin (tenant admin required)
- `/maintenance/:amoCode/admin`
- `/maintenance/:amoCode/admin/overview`
- `/maintenance/:amoCode/admin/amos`
- `/maintenance/:amoCode/admin/amo-profile`
- `/maintenance/:amoCode/admin/users`
- `/maintenance/:amoCode/admin/users/new`
- `/maintenance/:amoCode/admin/users/:userId`
- `/maintenance/:amoCode/admin/amo-assets`
- `/maintenance/:amoCode/admin/billing`
- `/maintenance/:amoCode/admin/invoices`
- `/maintenance/:amoCode/admin/invoices/:invoiceId`
- `/maintenance/:amoCode/admin/settings`
- `/maintenance/:amoCode/admin/email-logs`
- `/maintenance/:amoCode/admin/email-settings`

## Upsell
- `/maintenance/:amoCode/upsell`

import {test,expect} from '@playwright/test';
import {mockQualityShell} from './helpers/mockQualityShell';

test('email recovery uses the entered account and does not offer unavailable WhatsApp',async({page})=>{
 await mockQualityShell(page);let submitted:any;
 await page.route('**/auth/password-reset/channels',r=>r.fulfill({contentType:'application/json',body:'{"email":true,"whatsapp":false}'}));
 await page.route('**/auth/password-reset/request',r=>{submitted=r.request().postDataJSON();return r.fulfill({status:202,contentType:'application/json',body:'{"message":"If the account matches, a reset link will be sent to its registered contact details."}'});});
 await page.goto('/reset-password?amo=SAFARILINK&email=owner%40example.com');await expect(page.getByRole('textbox',{name:'Work email'})).toHaveValue('owner@example.com');await expect(page.getByText(/WhatsApp recovery is not currently available/)).toBeVisible();await expect(page.getByRole('combobox')).toHaveCount(0);
 await page.getByRole('button',{name:'Send reset link',exact:true}).click();await expect.poll(()=>submitted?.email).toBe('owner@example.com');expect(submitted.amo_slug).toBe('SAFARILINK');expect(submitted.delivery_method).toBe('email');await expect(page.getByText(/If the account matches/)).toBeVisible();await expect(page.getByRole('button',{name:'Copy reset link'})).toHaveCount(0);await page.screenshot({path:'../.artifacts/reset-email-request.png'});
});

test('unavailable recovery channels cannot produce a false sent confirmation',async({page})=>{
 await mockQualityShell(page);await page.route('**/auth/password-reset/channels',r=>r.fulfill({contentType:'application/json',body:'{"email":false,"whatsapp":false}'}));await page.goto('/reset-password?amo=safarilink');await expect(page.getByText('Password recovery is unavailable. Please contact your administrator.')).toBeVisible();await expect(page.getByRole('button',{name:'Send reset link',exact:true})).toBeDisabled();
});

test('WhatsApp is offered only when its provider is available',async({page})=>{
 await mockQualityShell(page);await page.route('**/auth/password-reset/channels',r=>r.fulfill({contentType:'application/json',body:'{"email":true,"whatsapp":true}'}));await page.goto('/reset-password?amo=safarilink');await expect(page.getByRole('combobox',{name:'Send reset link via'})).toBeVisible();await page.getByRole('combobox').selectOption('whatsapp');await expect(page.getByRole('combobox')).toHaveValue('whatsapp');
});

test('a received reset link opens password confirmation without another delivery request',async({page})=>{
 await mockQualityShell(page);let body:any;let channelRequests=0;
 await page.route('**/auth/password-reset/channels',r=>{channelRequests++;return r.fulfill({contentType:'application/json',body:'{"email":true,"whatsapp":false}'});});
 await page.route('**/auth/password-reset/confirm',r=>{body=r.request().postDataJSON();return r.fulfill({contentType:'application/json',body:'{"message":"Password reset successfully."}'});});
 await page.goto('/reset-password?amo=safarilink&token=synthetic-reset-token');await page.getByLabel('New password',{exact:true}).fill('DemoPassword!234');await page.getByLabel('Confirm new password',{exact:true}).fill('DemoPassword!234');await page.getByRole('button',{name:'Reset password',exact:true}).click();await expect(page.getByText('Your password has been reset. Please log in again.')).toBeVisible();expect(body.token).toBe('synthetic-reset-token');expect(channelRequests).toBe(0);
});

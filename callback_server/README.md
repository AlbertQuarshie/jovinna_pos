# Jovinna POS — M-Pesa callback server

A tiny Cloudflare Worker that receives Safaricom's STK Push results, so the POS can show and print the
**M-Pesa code** (e.g. `TJR4XYZ123`). It runs on Cloudflare's **free plan**.

The POS works without it (it asks Safaricom for each result itself); this only adds the M-Pesa code.

## One-time setup (about 15 minutes)

You need a free account at **cloudflare.com** and Node.js on the computer you set it up from.
Run these in this `callback_server` folder:

```bash
npx wrangler login
```
Opens the browser to approve access to your Cloudflare account.

```bash
npx wrangler d1 create jovinna-mpesa
```
Copy the `database_id` it prints into `wrangler.toml` (replace `PASTE_DATABASE_ID_HERE`).

```bash
npx wrangler d1 execute jovinna-mpesa --remote --file=schema.sql
```
Creates the payments table.

```bash
npx wrangler secret put APP_KEY
```
Type a long random password (e.g. 30+ letters and numbers) and **keep it**: the POS needs it.
Anyone with this key could read payment details, so don't share it.

```bash
npx wrangler deploy
```
Prints your server address, like `https://jovinna-mpesa.yourname.workers.dev`.

## Connect the POS

In Jovinna POS → **Settings**:

1. **Callback server**: the address from `wrangler deploy`
2. **Server key**: the APP_KEY you typed
3. Click **Test callback server** → "working", then **Save**

The line under the fields shows the exact callback address the POS gives Safaricom. Its last part is
derived from your key, so it can't be guessed.

## Good to know

- Payment records are deleted automatically after 90 days (the POS keeps its own copy with each sale).
- To change the key: run `npx wrangler secret put APP_KEY` again, then update **Server key** in the POS.
- Free plan limit is about 100,000 requests a day — far beyond what a shop uses.

# Smart Water Supply, Delivery & Reusable Bottle Tracking Platform

Django + MySQL — **Phase 1 (MVP)** implementation.

## যা এই কোডে আছে

- Custom User model (phone + OTP verification + Role-Based Access Control)
- Home Page, User Panel (customer dashboard, addresses, orders), Staff Panel
  (assigned deliveries, bottle exchange, cash handover), Admin Panel (Django
  Admin — customers, products, bottles, orders, payments, staff, reports)
- Reusable bottle business model: first purchase (bottle+water), refill
  (water only), damaged/lost → new bottle purchase — no QR/barcode, no
  mandatory damage photo, no deposit system
- Bottle lifecycle & audit trail (`bottles` app) — every status change is
  logged with who/when, since there's no QR code to rely on
- Order → Payment → Delivery workflow, with bKash/Nagad/COD payment methods
- **Payment gateways are placeholders** (`payments/gateways.py`) — they
  return a dummy success response so you can test the full order flow today;
  swap in real bKash/Nagad merchant API calls later without touching any
  other file
- Cash Reconciliation (`payments.CashHandover`) for COD cash handed over by
  staff at day's end
- Internal shrinkage / damage write-off is handled through
  `BottleTransaction` + `BottleUnit.status` (DAMAGED/RETIRED)
- Delivery exceptions, staff delivery incentive (flat rate, MVP), referral/
  loyalty points and promo code models are included (Phase 2, not yet wired
  into views — models + admin are ready so you can start using them)
- GPS ping & Offline sync event models are included for Phase 2 (not yet
  wired into a mobile client)
- **Guest Order** — order without creating an account first (name + phone +
  address, OTP-verified, a lightweight guest account is created behind the
  scenes so it fits the same Order/Payment/Bottle models)
- **Internal Shrinkage Write-off** — a proper Admin bulk action (select
  bottles in Django Admin → "Write off as Internal Shrinkage"), not just
  manually editing a field
- **Duplicate-order alert** — if a customer has an active auto-refill
  Subscription for a product, the order page shows a warning (doesn't
  block, per your instruction)
- **AuditLog** is now actually written to — order creation, out-for-delivery,
  bottle collect/issue, delivery complete, exceptions, cash handover
  submission, and shrinkage write-offs all log an entry
- **Promo Code redemption** — enter a code at checkout (both registered and
  guest), it's validated (active/date range/usage limit), discount applied
  to the order total, `used_count` incremented
- **Referral reward** — enter a referrer's phone number as a "referral code"
  at registration; when the referred user completes their first order, the
  referrer automatically gets loyalty points + a notification
- Fixed an OTP bug from the first draft where the expiry timestamp was set
  to "now" instead of "+5 minutes", which made every OTP invalid
  immediately

## What was added in the RBAC/GPS/B2B round (demo/simulated integrations)

Everything below is a **working demo**, not a real third-party integration
— but each one is built so swapping in real credentials later is a small,
contained change, not a rewrite.

- **SMS gateway** (`core/sms_gateway.py`) — OTPs now go through a demo
  `send_sms()` that logs every message to `core.SMSLog` (visible in Admin),
  same as a real provider's dashboard would. Swap the body of `send_sms()`
  for a real provider's API call later.
- **bKash/Nagad payment flow** — choosing bKash/Nagad at checkout now
  redirects to a demo payment page (`/payments/gateway/<id>/`) that mimics
  the real redirect-and-callback flow real gateways use, with
  Confirm/Cancel buttons. `payments/gateways.py` still has the
  `initiate_payment`/`verify_payment` stub functions — this just gives the
  full round-trip a visible UI so the checkout flow can be demoed end to
  end.
- **Granular RBAC** (`core/admin_mixins.py`) — Django Admin access is now
  restricted per role, not just is_staff/is_superuser. See
  `ROLE_APP_ACCESS` in that file: Accountant gets full access to Payments
  only (view-only elsewhere), View Only gets read-only everywhere,
  Operations Manager gets full access to Orders/Catalog/Bottles/Delivery,
  Warehouse Staff gets full access to Bottles, etc. Add a new role's rules
  by editing that one dictionary.
- **GPS tracking** — the Staff Panel now pings the browser's geolocation
  every 30s to `/staff/api/gps-ping/` (falls back to a local queue if
  offline). Admin/Ops/Delivery Manager roles can see the latest position
  per staff member at `/staff/gps-tracking/` (nav bar → "GPS Tracking").
  No Google Maps API key needed — it links out to Google Maps per point.
- **Offline sync** — the Staff Panel's browser JS queues events in
  `localStorage` while offline and flushes them to
  `/staff/api/offline-sync/` when back online. The endpoint is
  idempotent (safe to resend) and flags anything referencing an order it
  can't resolve as `CONFLICT` for manual review, rather than guessing.
- **B2B / Corporate module** (new `b2b` app) — `CorporateClient` model with
  a credit limit; `/b2b/dashboard/` lets a corporate contact place postpaid
  bulk orders (blocked if it would exceed their credit limit) and see
  invoices. Admin has a bulk action on Corporate Clients — "Generate
  invoice for all un-invoiced orders" — that bundles their un-invoiced
  orders into an `Invoice` with a due date based on their payment terms.

## Project layout

```
smartwater/       # project settings, urls
accounts/         # custom User, OTP, Address, Referral, LoyaltyPoint
catalog/          # Product
bottles/          # BottleUnit, BottleTransaction (lifecycle + audit)
orders/           # Order, OrderItem, DeliveryException, Subscription, RefillReminder
payments/         # Payment, CashHandover, PromoCode, gateways.py (placeholder)
delivery/         # Vehicle, GPSPing, OfflineSyncEvent, DeliveryIncentive, staff views
core/              # Home page, Notification, AuditLog, seed_demo_data command
templates/, static/
```

## MySQL setup

1. Install MySQL locally (or use XAMPP/WAMP's MySQL) and create a database:

   ```sql
   CREATE DATABASE smartwater_db CHARACTER SET utf8mb4;
   ```

2. Copy `.env.example` to `.env` and fill in your DB credentials:

   ```
   cp .env.example .env
   ```

   Edit `.env`:
   ```
   USE_MYSQL=True
   DB_NAME=smartwater_db
   DB_USER=root
   DB_PASSWORD=your_mysql_password
   DB_HOST=127.0.0.1
   DB_PORT=3306
   ```

   (If you don't have MySQL installed yet and just want to click around the
   app immediately, set `USE_MYSQL=False` in `.env` — it will use a local
   sqlite file instead. Nothing else changes.)

## Install & run

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt

python manage.py makemigrations
python manage.py migrate

# creates a demo Admin, Staff, Customer + 2 products so you can click around
python manage.py seed_demo_data

python manage.py runserver
```

Visit **http://127.0.0.1:8000/**

### Demo logins (created by `seed_demo_data`)

| Role     | Phone         | Password      | Where to log in      |
|----------|---------------|---------------|-----------------------|
| Admin    | 01700000000   | admin12345    | /admin/               |
| Staff    | 01900000001   | staffpass123  | /accounts/login/      |
| Customer | 01800000001   | custpass123   | /accounts/login/      |
| Accountant | 01500000001 | accountantpass | /admin/ (Payments full, rest view-only) |
| View Only  | 01500000002 | vieweronlypass | /admin/ (everything view-only) |
| Ops Manager| 01500000003 | opsmanagerpass | /admin/ (Orders/Catalog/Bottles/Delivery full) |
| Corporate Client | 01450000001 | corppass123 | /accounts/login/ then /b2b/dashboard/ |

Or create your own superuser: `python manage.py createsuperuser`

## OTP in dev mode

There's no real SMS gateway wired up yet. When you register, the OTP code
is printed to the **terminal/console** where `runserver` is running
(`[DEV OTP] phone=... code=123456`). Copy that code into the verification
page. Swap `accounts/views.py::_send_otp` for a real SMS API later.

## Trying the core flow

1. Log in as **Customer** → Order করুন → একটা product select করুন,
   address দিন, payment method দিন (COD সহজ testing-এর জন্য) → অর্ডার
   কনফার্ম করুন।
2. Log in as **Admin** (`/admin/`) → Orders → এই অর্ডারে `assigned_staff`
   সেট করুন এবং status = `ASSIGNED` করুন।
3. Log in as **Staff** → Staff Panel-এ অর্ডার দেখবেন → Out for Delivery →
   (refill হলে) Empty Bottle Collect → Full Bottle Deliver → Delivery
   Complete। COD হলে দিনশেষে Cash Handover পাতা থেকে জমা দিন।
4. Customer dashboard-এ ফিরে গিয়ে bottle status ও order history দেখুন।

## Trying the new demo integrations

- **SMS**: register/order-as-guest as usual; the OTP now shows up both in
  the terminal (`[DEMO SMS] ...`) and in Admin → SMS Logs.
- **bKash demo**: order with payment method bKash/Nagad → you'll land on a
  demo payment page → click Confirm to simulate success, or Cancel to
  simulate a failed/declined payment (order detail page will show a
  "retry" link).
- **RBAC**: log into `/admin/` as `01500000001` (Accountant) — you'll see
  Payments/Cash Handovers/Promo Codes with full edit rights, but Orders,
  Products, etc. only in read-only list/detail view (no Add/Delete
  buttons). Compare with `01500000002` (View Only) where nothing is
  editable, or `01500000003` (Ops Manager) where Orders/Bottles/Delivery
  are fully editable.
- **GPS**: log in as Staff (`01900000001`) on a device/browser that can
  grant location permission, open the Staff Panel and allow location — a
  ping is sent every 30s. Then log in as Admin and visit "GPS Tracking" in
  the nav bar.
- **Offline sync**: turn off your network in devtools while on the Staff
  Panel — the "Queued offline events" counter will start climbing; turn
  the network back on and it flushes automatically.
- **B2B**: log in as `01450000001` (Corporate Client contact), visit
  `/b2b/dashboard/`, place a bulk order — try a very large quantity first
  to see the credit-limit block, then a normal one. Then, as Admin, go to
  Admin → Corporate Clients → select the client → Action: "Generate
  invoice for all un-invoiced orders" to see the invoice appear on their
  dashboard.

## What was added in the UX/completeness round — customer cancellation, stock checks, etc.

- **Order cancellation** — customers can cancel an order while it's still
  `CREATED`/`CONFIRMED` (before staff assignment). Stock is restored for
  first-purchase orders and the payment is marked failed/void.
- **Stock check** — first-purchase orders now check `Product.available_stock`
  before creating the order and decrement it afterward; refill orders don't
  touch stock (water supply is treated as unlimited, only physical bottles
  are tracked).
- **Password reset** — `/accounts/forgot-password/` → OTP → set a new
  password. Goes through the same demo SMS gateway as registration.
- **Notification inbox** — the 🔔 badge in the navbar is now a link to a
  paginated notification list with a "mark all as read" button, instead of
  just a count.
- **Address edit** — addresses could only be added/deleted before; there's
  now an Edit page too.
- **Pagination** — added to the order list and product list (10–12 per
  page) so these don't become unusably long pages as data grows.
- **Order status timeline** — the order detail page now shows a visual
  step tracker (Created → Confirmed → Assigned → Out for Delivery →
  Delivered) instead of just a status label. Failed/Cancelled orders show
  a plain status badge instead of the timeline.
- **Mobile nav** — the navbar collapses into a hamburger menu below ~720px
  instead of overflowing.
- **Custom 404/500 pages** — branded instead of Django's default error
  pages (only shown when `DJANGO_DEBUG=False`).
- **Live price preview on the order form** — shows the water/bottle price
  breakdown and clearly labels first-purchase vs. refill *before* the
  customer confirms, so new customers aren't surprised that the first
  order includes the bottle price.

## What was added in the polish round (design/small features)

- **Favicon** added (`static/img/favicon.svg`)
- **Custom confirm modal** — Cancel Order / Delete Address no longer use
  the browser's ugly `confirm()` popup; any element with
  `data-confirm="message"` now opens a styled in-app modal (see the script
  at the bottom of `templates/base.html`)
- **Admin Dashboard Summary** (`/staff/dashboard-summary/`) — today's order
  count/revenue, pending deliveries, low-stock products, unresolved cash
  handovers, and an overall order-status breakdown, all in one page.
  Visible to Admin, Ops Manager, Delivery Manager, and Accountant roles.
- **Product search & price filter** on the product list page (`?q=` and
  `?max_price=`)
- **Printable order receipt** (`/orders/<id>/receipt/`) — a clean,
  print-optimized page with a "Print / Save as PDF" button. Uses the
  browser's own print-to-PDF rather than a server-side PDF library, so
  there's no extra dependency.
## What was added in the customer-research round (reorder + subscriptions)

Based on industry research on what actually keeps water-delivery customers
happy (fast reorder, self-service subscription control), two features were
added:

- **One-click Reorder** — every past order (except cancelled ones) now has
  a "🔁 আবার অর্ডার করুন" button on both the order list and order detail
  pages. It re-places the same product/quantity/address/payment method as
  a brand new order, still going through the normal stock check.
- **Self-service Subscriptions** (`/orders/subscriptions/`) — customers can
  create a recurring reminder (Weekly/Bi-weekly/Monthly/Custom interval)
  for a product+address, then pause/resume, skip just the next delivery
  (pushes `next_run_date` forward one interval), or delete it entirely --
  all without contacting support. Note: this manages the *schedule and
  reminder*, not automatic order placement yet -- see "What's next" for
  wiring that up.

## What was added in the operational-polish round (8 small UX fixes)

- **Staff workload visibility** — the Assign Staff page now shows each
  delivery staff's current active-order count (ASSIGNED/OUT_FOR_DELIVERY),
  sorted least-loaded first, so admin doesn't accidentally overload one
  person while another sits idle.
- **Admin order search** (`/staff/search/`, nav → "🔍 অর্ডার খুঁজুন") —
  search by phone number or (partial) Order ID instead of opening Django
  Admin for every support call.
- **Flash messages** now have a close (×) button and auto-fade after ~6
  seconds instead of sitting on the page until reload.
- **Empty states** (order list, dashboard) now show a clear "এখনই অর্ডার
  করুন" call-to-action instead of just plain text.
- **Dashboard reorder shortcut** — "🔁 সর্বশেষ অর্ডার আবার করুন" button on
  the customer dashboard, one tap from the most common action.
- **Nav badge for unassigned orders** — a red counter badge next to the
  admin nav links showing how many orders still need staff assignment, so
  it doesn't require opening the dashboard to notice a backlog.
- **Order list filter tabs** (সব/চলমান/সম্পন্ন/বাতিল) on the customer's
  order history page.
- **Phone number visual formatting** — any input with "phone" in its field
  id now displays as `017X XXX XXXX` while typing (display-only; the
  server-side `normalize_bd_phone()` already strips spaces/dashes, so
  nothing about validation changed).

## What's next (Phase 2/3, not in this build yet)

- Wire up Subscription/Auto-Refill scheduling (e.g. Celery beat) and Refill
  Reminder notifications
- Real bKash/Nagad merchant API credentials in `payments/gateways.py`
  (the demo redirect/callback UI is already built — just swap the dummy
  responses for real HTTP calls)
- Real SMS provider credentials in `core/sms_gateway.py::send_sms`
- A real live-updating map for GPS Tracking (currently a refresh-to-see
  list view; the ping-collection API and data model are production-ready)
- B2B: partial payments against an invoice, automatic overdue marking,
  downloadable PDF invoices
- REST API (Django REST Framework) if you want a separate mobile app for
  Staff/Customer instead of these server-rendered pages

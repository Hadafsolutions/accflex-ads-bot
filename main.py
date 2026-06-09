import os
import schedule
import time
import requests
from datetime import datetime, timedelta
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

# ── Config ────────────────────────────────────────────────────────────────────
CUSTOMER_ID = os.environ.get("GOOGLE_ADS_CUSTOMER_ID", "8823799088")
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "")
REPORT_HOUR = int(os.environ.get("REPORT_HOUR", "9"))

def get_client():
    config = {
        "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
        "use_proto_plus": True,
        "login_customer_id": os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID", CUSTOMER_ID),
    }
    return GoogleAdsClient.load_from_dict(config)

def date_range(days):
    end = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    return start, end

# ── Fetch Campaign Data ────────────────────────────────────────────────────────
def get_campaign_performance(days=1):
    client = get_client()
    service = client.get_service("GoogleAdsService")
    start, end = date_range(days)

    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            campaign.status,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions,
            metrics.ctr,
            metrics.average_cpc,
            metrics.cost_per_conversion,
            metrics.search_impression_share
        FROM campaign
        WHERE segments.date BETWEEN '{start}' AND '{end}'
        AND campaign.status != 'REMOVED'
        ORDER BY metrics.cost_micros DESC
    """

    response = service.search(customer_id=CUSTOMER_ID, query=query)
    campaigns = []
    for row in response:
        campaigns.append({
            "id": row.campaign.id,
            "name": row.campaign.name,
            "status": row.campaign.status.name,
            "impressions": row.metrics.impressions,
            "clicks": row.metrics.clicks,
            "cost": round(row.metrics.cost_micros / 1_000_000, 2),
            "conversions": round(row.metrics.conversions, 1),
            "ctr": round(row.metrics.ctr * 100, 2),
            "avg_cpc": round(row.metrics.average_cpc / 1_000_000, 2),
            "cpa": round(row.metrics.cost_per_conversion / 1_000_000, 2) if row.metrics.conversions > 0 else 0,
            "impression_share": round((row.metrics.search_impression_share or 0) * 100, 1),
        })
    return campaigns

# ── Fetch Ad Group Data ────────────────────────────────────────────────────────
def get_adgroup_performance(campaign_name=None, days=1):
    client = get_client()
    service = client.get_service("GoogleAdsService")
    start, end = date_range(days)

    where_clause = f"WHERE segments.date BETWEEN '{start}' AND '{end}' AND campaign.status != 'REMOVED'"
    if campaign_name:
        where_clause += f" AND campaign.name = '{campaign_name}'"

    query = f"""
        SELECT
            campaign.name,
            ad_group.id,
            ad_group.name,
            ad_group.status,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions,
            metrics.ctr,
            metrics.average_cpc
        FROM ad_group
        {where_clause}
        ORDER BY metrics.cost_micros DESC
    """

    response = service.search(customer_id=CUSTOMER_ID, query=query)
    adgroups = []
    for row in response:
        adgroups.append({
            "campaign": row.campaign.name,
            "id": row.ad_group.id,
            "name": row.ad_group.name,
            "status": row.ad_group.status.name,
            "impressions": row.metrics.impressions,
            "clicks": row.metrics.clicks,
            "cost": round(row.metrics.cost_micros / 1_000_000, 2),
            "conversions": round(row.metrics.conversions, 1),
            "ctr": round(row.metrics.ctr * 100, 2),
            "avg_cpc": round(row.metrics.average_cpc / 1_000_000, 2),
        })
    return adgroups

# ── Fetch Wasted Spend ─────────────────────────────────────────────────────────
def get_wasted_spend(campaign_name=None, days=7):
    client = get_client()
    service = client.get_service("GoogleAdsService")
    start, end = date_range(days)

    where_clause = f"WHERE segments.date BETWEEN '{start}' AND '{end}' AND metrics.clicks > 0 AND metrics.conversions = 0 AND metrics.cost_micros > 500000000"
    if campaign_name:
        where_clause += f" AND campaign.name = '{campaign_name}'"

    query = f"""
        SELECT
            campaign.name,
            search_term_view.search_term,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions
        FROM search_term_view
        {where_clause}
        ORDER BY metrics.cost_micros DESC
        LIMIT 20
    """

    response = service.search(customer_id=CUSTOMER_ID, query=query)
    terms = []
    for row in response:
        terms.append({
            "campaign": row.campaign.name,
            "term": row.search_term_view.search_term,
            "clicks": row.metrics.clicks,
            "cost": round(row.metrics.cost_micros / 1_000_000, 2),
            "conversions": row.metrics.conversions,
        })
    return terms

# ── Pause / Enable Ad Group ────────────────────────────────────────────────────
def set_adgroup_status(adgroup_id, status="ENABLED"):
    client = get_client()
    service = client.get_service("AdGroupService")
    op = client.get_type("AdGroupOperation")

    ag = op.update
    ag.resource_name = service.ad_group_path(CUSTOMER_ID, adgroup_id)
    ag.status = client.enums.AdGroupStatusEnum[status]

    fm = client.get_type("FieldMask")
    fm.paths.append("status")
    op.update_mask.CopyFrom(fm)

    response = service.mutate_ad_groups(customer_id=CUSTOMER_ID, operations=[op])
    return response.results[0].resource_name

# ── Add Negative Keywords ──────────────────────────────────────────────────────
def add_negative_keywords(campaign_id, keywords):
    client = get_client()
    service = client.get_service("CampaignCriterionService")
    campaign_service = client.get_service("CampaignService")

    operations = []
    for kw in keywords:
        op = client.get_type("CampaignCriterionOperation")
        criterion = op.create
        criterion.campaign = campaign_service.campaign_path(CUSTOMER_ID, campaign_id)
        criterion.negative = True
        criterion.keyword.text = kw
        criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum.BROAD
        operations.append(op)

    response = service.mutate_campaign_criteria(customer_id=CUSTOMER_ID, operations=operations)
    return f"Added {len(response.results)} negative keywords"

# ── Discord Reporter ───────────────────────────────────────────────────────────
def send_discord(message, title=None, color=0x00D4AA):
    if not DISCORD_WEBHOOK:
        print("No Discord webhook configured")
        return

    embed = {
        "title": title or "AccFlex Google Ads Report",
        "description": message,
        "color": color,
        "footer": {"text": f"AccFlex Ads Bot • {datetime.now().strftime('%Y-%m-%d %H:%M')}"},
    }
    payload = {"embeds": [embed]}
    r = requests.post(DISCORD_WEBHOOK, json=payload)
    print(f"Discord: {r.status_code}")

# ── Daily Report ───────────────────────────────────────────────────────────────
def daily_report():
    print(f"\n[{datetime.now()}] Running daily report...")
    try:
        campaigns = get_campaign_performance(days=1)
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        total_cost = sum(c["cost"] for c in campaigns)
        total_clicks = sum(c["clicks"] for c in campaigns)
        total_conv = sum(c["conversions"] for c in campaigns)
        total_impr = sum(c["impressions"] for c in campaigns)

        lines = [f"**Daily Report — {yesterday}**\n"]
        lines.append(f"Total Spend: **{total_cost:,.0f} EGP**")
        if total_impr > 0:
            lines.append(f"Clicks: **{total_clicks:,}** | CTR: **{total_clicks/total_impr*100:.2f}%**")
        lines.append(f"Conversions: **{total_conv:.0f}**")
        if total_conv > 0:
            lines.append(f"CPA: **{total_cost/total_conv:,.0f} EGP**")
        lines.append("\n**Campaigns:**")

        for c in campaigns:
            status_emoji = "ON" if c["status"] == "ENABLED" else "OFF"
            conv_str = f"Conv: {c['conversions']:.0f}" if c["conversions"] > 0 else "0 conv"
            lines.append(f"[{status_emoji}] **{c['name']}** — {c['cost']:,.0f} EGP | {c['clicks']} clicks | {conv_str}")

        # Alerts
        alerts = []
        for c in campaigns:
            if c["cost"] > 1000 and c["conversions"] == 0:
                alerts.append(f"ALERT: **{c['name']}** spent {c['cost']:,.0f} EGP with 0 conversions!")
            if c["ctr"] < 1.0 and c["impressions"] > 100:
                alerts.append(f"WARNING: **{c['name']}** CTR very low: {c['ctr']}%")

        if alerts:
            lines.append("\n**Alerts:**")
            lines.extend(alerts)

        message = "\n".join(lines)
        send_discord(message, title=f"Daily Report — {yesterday}", color=0x0E1B5C)
        print(message)

    except Exception as e:
        error_msg = f"Daily report failed: {str(e)}"
        send_discord(error_msg, color=0xFF0000)
        print(error_msg)

# ── Initial Optimizations ──────────────────────────────────────────────────────
def run_initial_optimizations():
    print("\nRunning initial optimizations for KSA (May) #2...")
    try:
        client = get_client()
        ga_service = client.get_service("GoogleAdsService")

        query = """
            SELECT campaign.id, campaign.name, ad_group.id, ad_group.name, ad_group.status
            FROM ad_group
            WHERE campaign.name = 'KSA (May) #2'
        """
        response = ga_service.search(customer_id=CUSTOMER_ID, query=query)

        campaign_id = None
        accounting_ag_id = None

        for row in response:
            campaign_id = row.campaign.id
            ag_name = row.ad_group.name.lower()
            ag_status = row.ad_group.status.name
            print(f"  Ad Group: {row.ad_group.name} ({ag_status}) — ID: {row.ad_group.id}")
            if "accounting" in ag_name:
                accounting_ag_id = row.ad_group.id

        if not campaign_id:
            print("Campaign 'KSA (May) #2' not found")
            send_discord("Campaign 'KSA (May) #2' not found. Check campaign name.", color=0xFF0000)
            return

        print(f"Found campaign ID: {campaign_id}")

        # 1. Add Negative Keywords
        print("\nAdding negative keywords...")
        neg_keywords = [
            "دفترة", "سماك", "dexef", "zoho", "وافق", "ملاذ",
            "مقاولين", "تنفيذ مشاريع", "منصة المشاريع", "وظائف", "فرص عمل",
            "daftera", "doubleclick"
        ]
        result = add_negative_keywords(campaign_id, neg_keywords)
        print(f"  {result}")

        # 2. Enable Accounting Ad Group
        if accounting_ag_id:
            print(f"\nEnabling Accounting ad group (ID: {accounting_ag_id})...")
            set_adgroup_status(accounting_ag_id, "ENABLED")
            print("  Enabled successfully")
        else:
            print("  Accounting ad group not found")

        msg = (
            "**Initial Optimizations Applied — KSA (May) #2**\n\n"
            f"Added **{len(neg_keywords)} negative keywords** (competitors + irrelevant)\n"
            f"Accounting ad group: **ENABLED**\n"
            f"Daily monitoring: **ACTIVE** at {REPORT_HOUR}:00\n\n"
            "Negatives added: " + ", ".join(neg_keywords)
        )
        send_discord(msg, title="KSA (May) #2 — Optimizations Applied", color=0x00D4AA)
        print("\nAll optimizations applied successfully!")

    except GoogleAdsException as ex:
        for error in ex.failure.errors:
            print(f"Google Ads Error: {error.message}")
        send_discord(f"Optimization failed: {ex.failure.errors[0].message}", color=0xFF0000)
    except Exception as e:
        print(f"Error: {e}")
        send_discord(f"Optimization error: {str(e)}", color=0xFF0000)

# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("AccFlex Google Ads Bot starting...")
    print(f"  Customer ID: {CUSTOMER_ID}")
    print(f"  Daily report time: {REPORT_HOUR}:00")
    print(f"  Discord: {'configured' if DISCORD_WEBHOOK else 'NOT configured'}")

    run_initial_optimizations()

    schedule.every().day.at(f"{REPORT_HOUR:02d}:00").do(daily_report)
    print(f"\nDaily report scheduled at {REPORT_HOUR:02d}:00")
    print("Bot is running...\n")

    daily_report()

    while True:
        schedule.run_pending()
        time.sleep(60)

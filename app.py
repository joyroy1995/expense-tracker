from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from functools import wraps
from datetime import datetime
import database as db
from llm_service import extract_expense, predict_expense
from config import USERNAME, PASSWORD, SECRET_KEY, CATEGORY_COLORS

app = Flask(__name__)
app.secret_key = SECRET_KEY

db.init_db()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "logged_in" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if username == USERNAME and password == PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("index"))
        return render_template("login.html", error="Invalid credentials")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    today = datetime.now().strftime("%Y-%m-%d")
    today_expenses = db.get_expenses_by_date(today)
    today_total = db.get_today_total()
    month_total = db.get_month_total()
    recent_expenses = db.get_all_expenses(limit=30)
    return render_template(
        "index.html",
        today_expenses=today_expenses,
        today_total=today_total,
        month_total=month_total,
        recent_expenses=recent_expenses,
        today=today,
        category_colors=CATEGORY_COLORS,
    )


@app.route("/dashboard")
@login_required
def dashboard():
    now = datetime.now()
    year = request.args.get("year", now.year, type=int)
    month = request.args.get("month", now.month, type=int)

    category_totals = db.get_category_totals_by_month(year, month)
    monthly_totals = db.get_monthly_totals(months=6)
    month_expenses = db.get_expenses_by_month(year, month)

    month_total = sum(t["total"] for t in category_totals)

    return render_template(
        "dashboard.html",
        category_totals=category_totals,
        monthly_totals=monthly_totals,
        month_expenses=month_expenses,
        year=year,
        month=month,
        month_total=month_total,
        category_colors=CATEGORY_COLORS,
    )


@app.route("/api/add_expense", methods=["POST"])
@login_required
def api_add_expense():
    data = request.get_json()
    description = data.get("description", "").strip()

    if not description:
        return jsonify({"error": "Description required"}), 400

    result = extract_expense(description)
    category = result["category"]
    amount = result["amount"]

    if amount <= 0:
        return jsonify({"error": "Could not extract amount. Please include the amount in your text."}), 400

    today = datetime.now().strftime("%Y-%m-%d")
    expense_id = db.add_expense(today, description, amount, category)

    return jsonify(
        {
            "id": expense_id,
            "date": today,
            "description": description,
            "amount": amount,
            "category": category,
            "color": CATEGORY_COLORS.get(category, "#6b7280"),
        }
    )


@app.route("/api/predict_expense", methods=["POST"])
@login_required
def api_predict_expense():
    data = request.get_json()
    description = data.get("description", "").strip()

    if len(description) < 2:
        return jsonify({"category": None, "amount": None})

    result = predict_expense(description)
    if result:
        return jsonify(
            {
                "category": result["category"],
                "amount": result["amount"],
                "color": CATEGORY_COLORS.get(result["category"], "#6b7280"),
            }
        )
    return jsonify({"category": None, "amount": None})


@app.route("/api/delete_expense/<int:expense_id>", methods=["DELETE"])
@login_required
def api_delete_expense(expense_id):
    db.delete_expense(expense_id)
    return jsonify({"success": True})


@app.route("/api/expenses/<date>")
@login_required
def api_expenses_by_date(date):
    expenses = db.get_expenses_by_date(date)
    for exp in expenses:
        exp["color"] = CATEGORY_COLORS.get(exp["category"], "#6b7280")
    return jsonify(expenses)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

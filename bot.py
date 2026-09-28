import asyncio
import math
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

TOKEN = "8933139058:AAHsnwlPV5d1KXtIa87g3gMo3U3dJ7j8qE0"

# Мини-сервер, чтобы Render был доволен открытым портом
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()

# Запускаем веб-сервер в фоновом потоке
threading.Thread(target=run_server, daemon=True).start()

bot = Bot(token=TOKEN)
dp = Dispatcher()


def poisson_prob(lmbda, k):
  return (lmbda**k * math.exp(-lmbda)) / math.factorial(k)


def dixon_coles_factor(i, j, lmbda1, lmbda2, rho=-0.12):
  if i == 0 and j == 0:
    return 1.0 - (lmbda1 * lmbda2 * rho)
  elif i == 0 and j == 1:
    return 1.0 + (lmbda1 * rho)
  elif i == 1 and j == 0:
    return 1.0 + (lmbda2 * rho)
  elif i == 1 and j == 1:
    return 1.0 - rho
  else:
    return 1.0


def remove_margin_power_method(odds_1, odds_x, odds_2):
  inv_sum = (1 / odds_1) + (1 / odds_x) + (1 / odds_2)
  if inv_sum <= 1:
    return 1 / odds_1, 1 / odds_x, 1 / odds_2, 0.0
  k = 1.0
  for _ in range(50):
    s = (
        (1 / odds_1) ** k
        + (1 / odds_x) ** k
        + (1 / odds_2) ** k
    )
    if abs(s - 1.0) < 1e-5:
      break
    k += (s - 1.0) * 0.1
  return (1 / odds_1) ** k, (1 / odds_x) ** k, (1 / odds_2) ** k, (inv_sum - 1.0) * 100


def calculate_risk_of_ruin(win_prob, odds, bankroll, stake):
  edge = (win_prob * odds) - 1.0
  if edge <= 0:
    return 100.0
  try:
    ruin = math.exp(-2.0 * edge * (bankroll / stake) / (odds * odds))
    return min(max(ruin * 100.0, 0.0), 100.0)
  except OverflowError:
    return 100.0


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
  text = (
      "⚡ **Quant Football Bot v14.0**\n\n"
      "Отправь команду для квант-анализа матча в формате:\n"
      "`/match Хозяева | xG1 | Отдых1 | Гости | xG2 | Отдых2 | П1 | X | П2`\n\n"
      "📌 **Пример:**\n"
      "`/match Норвегия | 1.65 | 4 | Португалия | 1.40 | 3 | 2.40 | 3.30 | 3.00`"
  )
  await message.answer(text, parse_mode="Markdown")


@dp.message(Command("match"))
async def cmd_match(message: types.Message):
  try:
    args = message.text.replace("/match", "").strip()
    parts = [p.strip() for p in args.split("|")]
    if len(parts) != 9:
      await message.answer(
          "❌ **Ошибка формата!**\nИспользуй строго:"
          " `/match Хозяева | xG1 | Отдых1 | Гости | xG2 | Отдых2 | П1 | X | П2`",
          parse_mode="Markdown",
      )
      return

    t1, xg1, rest1, t2, xg2, rest2, o1, ox, o2 = (
        parts[0],
        float(parts[1]),
        int(parts[2]),
        parts[3],
        float(parts[4]),
        int(parts[5]),
        float(parts[6]),
        float(parts[7]),
        float(parts[8]),
    )

    fatigue1 = 0.93 if rest1 < 4 else 1.0
    fatigue2 = 0.93 if rest2 < 4 else 1.0
    t1_final_xg = xg1 * 1.12 * fatigue1
    t2_final_xg = xg2 * fatigue2

    max_goals = 6
    raw_matrix = []
    total_prob_sum = 0.0

    for i in range(max_goals + 1):
      for j in range(max_goals + 1):
        p_base = poisson_prob(t1_final_xg, i) * poisson_prob(t2_final_xg, j)
        dc_adj = dixon_coles_factor(i, j, t1_final_xg, t2_final_xg, rho=-0.12)
        adjusted_prob = max(0.0, p_base * dc_adj)
        raw_matrix.append((i, j, adjusted_prob))
        total_prob_sum += adjusted_prob

    score_matrix = []
    p_win1, p_draw, p_win2 = 0.0, 0.0, 0.0
    for i, j, prob in raw_matrix:
      norm_prob = prob / total_prob_sum if total_prob_sum > 0 else 0
      score_matrix.append((i, j, norm_prob))
      if i > j:
        p_win1 += norm_prob
      elif i == j:
        p_draw += norm_prob
      else:
        p_win2 += norm_prob

    score_matrix.sort(key=lambda x: x[2], reverse=True)
    true_p1, true_px, true_p2, margin = remove_margin_power_method(o1, ox, o2)

    ev_percent = ((p_win1 * o1) - 1) * 100
    kelly = ((p_win1 * o1) - 1) / (o1 - 1) if o1 > 1 else 0
    bankroll = 35.0
    stake = max(bankroll * kelly * 0.25, 1.0) if kelly > 0 else 1.0
    ruin = calculate_risk_of_ruin(p_win1, o1, bankroll, stake)

    response = (
        f"⚡ **КВАНТ-АНАЛИЗ: {t1} vs {t2}**\n\n"
        f"🏠 xG с учетом усталости: `{t1_final_xg:.2f}` | `{t2_final_xg:.2f}`\n"
        f"📉 Маржа БК: `{margin:.2f}%`\n\n"
        f"🏆 **Топ-счет:** `{t1} {score_matrix[0][0]}:{score_matrix[0][1]}`"
        f" `{t2}` (`{score_matrix[0][2]*100:.1f}%`)\n\n"
        f"📊 **Вероятности (Модель / БК без маржи):**\n"
        f"• П1: `{p_win1*100:.1f}%` | `{true_p1*100:.1f}%`\n"
        f"• Ничья: `{p_draw*100:.1f}%` | `{true_px*100:.1f}%`\n"
        f"• П2: `{p_win2*100:.1f}%` | `{true_p2*100:.1f}%`\n\n"
        f"📌 **Вердикт по П1 ({t1}):**\n"
        f"• EV (Ожидание): `{ev_percent:+.2f}%`\n"
        f"• Рекоменд. ставка (банк 35 сом): `{stake:.1f} сом`\n"
        f"• Риск разорения: `{ruin:.1f}%`"
    )
    await message.answer(response, parse_mode="Markdown")

  except Exception as e:
    await message.answer(
        f"⚠️ Ошибка в данных. Проверь правильность ввода.\nДетали: {e}"
    )


async def main():
  print("Бот и веб-сервер запущены...")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())

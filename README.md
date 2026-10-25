# Krónan Snjallverslun for Home Assistant

*Íslenska fyrir neðan.*

An unofficial Home Assistant integration for [Krónan](https://kronan.is) Snjallverslun, the online store of the Icelandic grocery chain. It uses Krónan's public API (in beta) with a personal access token.

Not affiliated with or endorsed by Krónan. The Krónan name and logo in `custom_components/kronan/brand/` belong to Krónan and are used only to identify the service in Home Assistant; they are not covered by this repository's license.

## What you get

| Entity | What it shows |
|---|---|
| `sensor.kronan_next_delivery` | Start of the next delivery or pickup window, with the end time, status, items, total, store and how much is still needed for free delivery as attributes |
| `sensor.kronan_cart_items` | Number of items in the cart, with the item list and the amount still needed for free delivery |
| `sensor.kronan_cart_total` | Cart total in ISK |
| `calendar.kronan_deliveries` | Your deliveries and pickups as calendar events |
| `todo.kronan_shopping_list` | The shopping note from the Krónan app as a to-do list. Add, rename, tick off and remove items in Home Assistant or with Assist, and they change in the Krónan app too |

The integration polls every 5 minutes, four requests each time. That is well inside the API limit of 200 requests per 200 seconds.

## Installation

1. In HACS, open the menu → **Custom repositories**, add `https://github.com/appkas/ha-kronan` as an **Integration**, then download **Krónan Snjallverslun**.
2. Restart Home Assistant.
3. Create an access token in Krónan Snjallverslun under your user settings. You need to sign in with Auðkenni. Tokens start with `act_`.
4. **Settings → Devices & services → Add integration → Krónan Snjallverslun**, and paste the token.

When a token expires or is revoked, Home Assistant asks for a new one.

## Notes

- The API is in beta and may change. Please open an issue if something stops working.
- Your token can place and change orders through the API. This integration only reads orders and the cart, and only writes to the shopping note.
- Diagnostics leave out the token and your address.

---

## Á íslensku

Óopinber samþætting fyrir Home Assistant við Snjallverslun [Krónunnar](https://kronan.is). Hún notar opið API Krónunnar (beta) með persónulegum aðgangslykli. Verkefnið tengist Krónunni ekki.

**Það sem þú færð:**
- **Næsta afhending:** hvenær næsta pöntun kemur, hvenær tímaglugginn lokar, staða, vörur, upphæð, og hve mikið vantar upp á fría heimsendingu.
- **Karfan:** fjöldi vara og samtala.
- **Dagatal** með afhendingum.
- **Innkaupalistinn** úr Krónuappinu sem verkefnalisti í HA. Það sem þú bætir við eða hakar við í HA, eða með raddaðstoðinni, breytist líka í appinu.

**Uppsetning:**
1. Í HACS bætirðu `https://github.com/appkas/ha-kronan` við sem sérsniðinni geymslu (*Integration*) og sækir **Krónan Snjallverslun**.
2. Endurræstu Home Assistant.
3. Búðu til aðgangslykil í notandastillingum Snjallverslunarinnar. Til þess þarf innskráningu með Auðkenni.
4. Farðu í **Stillingar → Tæki og þjónustur → Bæta við samþættingu → Krónan Snjallverslun** og límdu inn lykilinn.

## License

MIT, except the Krónan logo files in `custom_components/kronan/brand/`, which belong to Krónan.

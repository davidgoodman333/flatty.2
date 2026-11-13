"""Hand-written bootstrap examples for the risk classifier.

These are NOT real listings. The scam examples follow patterns that Swiss police and
consumer organisations warn about (owner abroad, keys by post, deposit before viewing,
payment via "Airbnb"/escrow/Western Union, contact via WhatsApp, price far below market).
All e-mail addresses use the reserved .example domain (RFC 2606), so none can belong to a real
person. They exist only so the first model can be trained before the expert-rated corpus from
the interviews is ready. Expert labels in data/labels/risk_labels.csv take precedence.
"""

SCAMS = [
    ("Schöne 3.5-Zimmer Wohnung Länggasse", "Ich bin zurzeit im Ausland wegen meiner Arbeit und kann die Wohnung leider nicht zeigen. Die Schlüssel werden per Post zugeschickt, nachdem Sie die Kaution von 2 Monatsmieten vorab überwiesen haben. Bitte kontaktieren Sie mich per E-Mail an hans.meier1960@gmail.example.", 890, 3.5, 80, False),
    ("Helle Wohnung im Breitenrain, sofort frei", "Die Wohnung ist möbliert und sofort bezugsbereit. Ich lebe derzeit in London. Die Zahlung der Kaution erfolgt sicher über Airbnb, danach erhalten Sie die Schlüssel. Schreiben Sie mir direkt per WhatsApp +44 7700 900123.", 750, 2.5, 65, False),
    ("Studio near University of Bern", "Hello, I am the owner of this lovely studio. I am currently abroad in Spain for work so viewing is not possible. Keys will be sent by DHL after the deposit is paid via Western Union. Please contact me at studio.bern.owner@outlook.example.", 450, 1.0, 35, False),
    ("4-Zimmer Altbauwohnung Altstadt", "Wunderschöne Altbauwohnung. Leider wohne ich im Ausland. Eine Besichtigung ist nicht möglich, aber ich sende Ihnen gerne mehr Fotos. Die erste Monatsmiete und das Depot bitte im Voraus überweisen, dann schicke ich den Vertrag und die Schlüssel.", 1100, 4.0, 110, False),
    ("Appartement meublé 2.5 pièces Berne", "Bonjour, je suis actuellement à l'étranger pour une mission humanitaire. Pas de visite possible. Le dépôt de caution se fait avant la visite par virement, ensuite les clés sont envoyées par la poste. Écrivez-moi à marie.dubois.location@yahoo.example.", 700, 2.5, 60, False),
    ("WG-Zimmer Mattenhof, alles inklusive", "Sehr dringend! Zimmer in schöner WG. Ich bin momentan im Ausland, Besichtigung nicht möglich. Bitte überweisen Sie die Kaution vorab über unseren Treuhand-Service, danach bekommen Sie die Schlüssel per Post.", 350, 1.0, 18, False),
    ("Bright apartment in Bern city centre", "Dear tenant, my late father's apartment is available. I live in the UK and cannot show it. To reserve, please pay the first month and deposit in advance through Airbnb payment protection. Contact me directly at james.walker.bern@gmail.example or WhatsApp.", 800, 3.0, 75, False),
    ("Moderne 2-Zimmer Wohnung Wankdorf", "Ich vermiete meine Wohnung, da ich beruflich nach Dubai gezogen bin. Keine Besichtigung möglich. Nach Erhalt der Kaution per Western Union sende ich Ihnen die Schlüssel. First come, first served.", 690, 2.0, 55, False),
    ("Möbliertes Studio Bern Monbijou", "Das Studio ist komplett möbliert. Ich befinde mich momentan im Ausland. Senden Sie mir bitte eine Kopie Ihres Passes und überweisen Sie das Depot vorab, dann reserviere ich das Studio für Sie. Kontakt nur per WhatsApp.", 520, 1.0, 30, False),
    ("Grosszügige Wohnung mit Balkon Kirchenfeld", "Wegen Auslandsaufenthalt vermiete ich meine Wohnung sehr günstig. Die Schlüssel werden versendet, sobald die Anzahlung über Airbnb eingegangen ist. Kontaktieren Sie mich direkt per E-Mail: wohnung.kirchenfeld@gmx.example", 980, 4.5, 105, False),
    ("Room in shared flat, Länggasse", "Hi! Nice room for students. I am in Italy at the moment so I can't show the room, but my agent will send you the keys after you transfer the deposit in advance. Write me on Telegram.", 300, 1.0, 16, False),
    ("3-Zimmer Wohnung Bümpliz sofort", "Ich bin zurzeit im Ausland und suche einen zuverlässigen Mieter. Bitte überweisen Sie die Kaution vorab, Besichtigung ist nicht möglich. Schnell entscheiden, viele Interessenten!", 650, 3.0, 70, False),
    ("Studio meublé proche de la gare", "Je suis à l'étranger, pas de visite. Paiement de la caution par MoneyGram, ensuite je vous envoie les clés. Contactez-moi sur WhatsApp.", 480, 1.0, 28, False),
    ("Charming flat Old Town Bern", "Beautiful historic flat. I moved to Canada so viewing is not possible. Payment through escrow service, keys will be shipped. Please email me at oldtown.flat.bern@hotmail.example with your passport copy.", 900, 3.5, 85, False),
    ("Wohnung mit Aussicht, Lorraine", "Ich vermiete meine Wohnung, weil ich ins Ausland gezogen bin. Die Kaution von CHF 1500 bitte vorab über Airbnb bezahlen. Schlüssel per Post. Schreiben Sie mir direkt per E-Mail.", 760, 3.0, 72, False),
    ("Neues Studio Bern West", "Sehr günstiges Studio. Keine Besichtigung, ich bin im Ausland. Zahlung per Bitcoin oder Western Union möglich. Schlüssel werden per Post verschickt.", 400, 1.0, 32, False),
    ("Apartment for students near Uni", "Perfect for international students! I am currently overseas. Pay the deposit in advance with PayPal Friends and I send keys and contract by post. Contact me on WhatsApp only.", 550, 2.0, 50, False),
    ("Familienwohnung 5.5 Zimmer Schosshalde", "Wegen Versetzung im Ausland. Besichtigung nicht möglich. Kaution vorab an unsere Treuhand-Agentur überweisen. Danach Vertrag und Schlüssel per Post. Bitte kontaktieren Sie mich per E-Mail.", 1350, 5.5, 140, False),
    ("Zimmer in WG, Breitenrain", "Ich bin derzeit im Ausland für ein Praktikum. Bitte zuerst die Kaution überweisen, dann schicke ich die Schlüssel. Kontakt via WhatsApp.", 320, 1.0, 15, False),
    ("Luxus-Attika Wohnung Bern", "Einmalige Gelegenheit! Ich lebe in Frankreich und vermiete meine Attikawohnung günstig. Besichtigung ist nicht möglich. Bitte Depot vorab über Airbnb überweisen, Schlüssel per Post.", 1200, 4.5, 130, False),
    ("Cosy 2-room apartment Bern", "Hello, I'm a doctor working abroad. The apartment is fully furnished. I can't show it, but after the deposit is paid by bank transfer in advance my lawyer will send the keys. Email: dr.anna.keller@gmail.example", 620, 2.0, 52, False),
    ("Appartement 3 pièces lumineux", "Je vis actuellement à l'étranger. La visite n'est pas possible, les clés seront envoyées après paiement de la caution par Western Union. Urgent.", 690, 3.0, 68, False),
    ("Studio im Zentrum, alles inklusive", "Ich bin im Ausland und kann das Studio nicht zeigen. Bitte senden Sie mir Ihre Ausweiskopie und überweisen Sie die erste Miete im Voraus. Danach erhalten Sie die Schlüssel per Post. Kontakt nur per E-Mail.", 430, 1.0, 26, False),
    ("2.5-Zimmer Wohnung Holligen", "Wohnung frei ab sofort. Da ich im Ausland lebe, läuft die Vermietung über Airbnb. Die Kaution wird über Airbnb bezahlt, danach Schlüsselübergabe per Kurier.", 710, 2.5, 60, False),
    ("Room for rent, all inclusive", "Room available now, very cheap. I live abroad, so no viewings. Send deposit in advance via Western Union and I will mail the keys. Contact me on WhatsApp +234 801 234 5678.", 280, 1.0, 14, False),
    ("Gemütliche Dachwohnung Weissenbühl", "Ich bin aus beruflichen Gründen im Ausland. Eine Besichtigung ist leider nicht möglich. Bei Interesse überweisen Sie bitte das Depot vorab. Kontaktieren Sie mich per E-Mail unter dachwohnung.bern@outlook.example", 740, 2.5, 62, False),
    ("Studio Länggasse", "Studio zu vermieten, sehr dringend. Ich bin im Ausland, Schlüssel werden zugeschickt. Kaution vorab per Überweisung.", 420, 1.0, 25, False),
    ("Wohnung 3.5 Zimmer Ostermundigen", "Ich vermiete meine Wohnung günstig, da ich ins Ausland gezogen bin. Zahlung über Airbnb, Schlüssel per Post. Bitte nur per WhatsApp schreiben.", 780, 3.5, 82, False),
]

LEGIT = [
    ("3.5-Zimmer-Wohnung an ruhiger Lage", "Wir vermieten per 1. April eine helle 3.5-Zimmer-Wohnung mit Balkon. Die Wohnung verfügt über eine moderne Küche mit Geschirrspüler und Parkettböden. Besichtigung am Samstag, 14 Uhr. Bitte melden Sie sich über das Kontaktformular an. Die Verwaltung freut sich auf Ihre Bewerbung.", 1950, 3.5, 82, False),
    ("Zimmer in netter 3er-WG", "Wir sind zwei Studierende (Uni Bern) und suchen ab Mai eine neue Mitbewohnerin oder einen Mitbewohner. Das Zimmer ist 14 m² gross, Küche und Bad werden geteilt. Komm doch am Donnerstagabend zum WG-Casting vorbei!", 620, 1.0, 14, True),
    ("Studio in der Länggasse", "Kleines Studio mit Kochnische und Dusche/WC, ideal für Studierende. Nähe Universität, Bus vor der Haustür. Besichtigungstermin nach Vereinbarung über die Plattform. Mietzins inkl. Nebenkosten.", 980, 1.0, 28, True),
    ("Charmante Altbauwohnung Breitenrain", "Schöne 2.5-Zimmer-Altbauwohnung mit hohen Decken, Parkett und Balkon. Waschmaschine im Keller. Besichtigung: Dienstag 18:00. Bewerbungsunterlagen (Betreibungsauszug, Lohnausweis) bitte nach der Besichtigung einreichen.", 1680, 2.5, 64, False),
    ("Room in shared flat near Uni Bern", "We are three students looking for a new flatmate from September. The room is furnished and 15 m². Viewing possible on Wednesday evening or via video call if you are still abroad. Rent includes utilities and internet.", 690, 1.0, 15, True),
    ("Moderne 4.5-Zimmer-Wohnung", "Erstvermietung nach Totalsanierung. Offene Küche, zwei Nasszellen, Lift, Einstellhallenplatz optional. Besichtigungen finden am 12. und 14. statt. Anmeldung über Flatfox.", 2650, 4.5, 105, False),
    ("Befristetes Zimmer Untermiete", "Ich bin für ein Auslandsemester weg und vermiete mein möbliertes Zimmer von Februar bis Juli in Untermiete. Besichtigung mit meinen Mitbewohnern jederzeit möglich. Bezahlt wird direkt an die Verwaltung.", 580, 1.0, 13, True),
    ("2-Zimmer-Wohnung Mattenhof", "Gepflegte 2-Zimmer-Wohnung im 3. OG, ohne Lift. Keller- und Estrichabteil, gemeinsame Waschküche. Haustiere auf Anfrage. Besichtigung am Montag um 17.30 Uhr.", 1390, 2.0, 52, False),
    ("Appartement 3 pièces proche gare", "Appartement lumineux de 3 pièces avec balcon. Cuisine agencée, salle de bain rénovée. Visite le samedi 10h, inscription via la plateforme. Dossier complet demandé après la visite.", 1790, 3.0, 70, False),
    ("Helles Studio mit Balkon", "Das Studio befindet sich in einem gepflegten Mehrfamilienhaus. Einbauküche, Balkon, Waschturm. Ideal für Studentinnen und Studenten oder Berufseinsteiger. Besichtigung nach Vereinbarung.", 1050, 1.5, 34, False),
    ("WG-Zimmer in Lorraine", "Gemütliches Zimmer in einer lebhaften 4er-WG. Wir kochen oft zusammen. Melde dich mit ein paar Sätzen über dich, dann laden wir dich zur Besichtigung ein.", 560, 1.0, 12, True),
    ("Familienwohnung mit Garten", "5.5-Zimmer-Wohnung im Erdgeschoss mit eigenem Gartensitzplatz. Nähe Schulen und Einkaufsmöglichkeiten. Besichtigung: Samstag 11:00. Kontakt über die Bewirtschaftung.", 2890, 5.5, 128, False),
    ("Möbliertes Studio, befristet 6 Monate", "Voll möbliertes Studio für 6 Monate, ideal für Austauschstudierende. Besichtigung vor Ort oder per Videocall möglich. Mietvertrag mit der Liegenschaftsverwaltung, Mietkaution auf ein gesperrtes Mietkautionskonto.", 1150, 1.0, 30, False),
    ("Bright 2.5-room flat", "Bright flat on the 2nd floor with balcony and view. Fully renovated kitchen and bathroom. Viewing on Thursday at 6 pm, please register via the platform. The deposit is paid into a rent deposit account after signing the contract.", 1720, 2.5, 58, False),
    # Legitimate listings that contain ONE harmless signal, so a single flag is not treated as proof of a scam.
    ("Zimmer in 4er-WG Breitenrain", "Wir suchen ab Dezember eine neue Mitbewohnerin oder einen Mitbewohner. Schreib uns per WhatsApp ein paar Zeilen über dich, dann laden wir dich zum Kennenlernen ein. Besichtigung jederzeit möglich.", 640, 1.0, 13, True),
    ("Untermiete während Auslandaufenthalt", "Ich arbeite ab Januar für sechs Monate im Ausland und vermiete meine Wohnung in Untermiete. Meine Nachbarin zeigt dir die Wohnung gerne, Besichtigung am Wochenende. Der Vertrag läuft über die Verwaltung.", 1350, 2.0, 48, True),
    ("Günstiges Zimmer, Familienanschluss", "Kleines Zimmer im Einfamilienhaus, ideal für Studierende. Sehr günstig, weil wir etwas Hilfe im Garten schätzen. Kommen Sie gerne zur Besichtigung vorbei, Termin nach Absprache.", 380, 1.0, 11, True),
    ("Studio, kurzfristig frei", "Studio ab sofort frei, da die Vormieterin kurzfristig gekündigt hat. Dringend, wir möchten schnell weitervermieten. Besichtigung morgen um 18 Uhr möglich, Anmeldung über die Plattform.", 1080, 1.0, 29, False),
    ("Room in shared flat for exchange student", "I am leaving for an exchange semester abroad and sublet my furnished room from February to July. My flatmates can show you the room, or we do a video call. Contact me via WhatsApp or the platform.", 610, 1.0, 14, True),
    ("Chambre en colocation", "Chambre meublée dans une colocation sympa. Visite possible le soir, contactez-nous par WhatsApp. La caution est versée sur un compte de garantie après la signature du bail.", 700, 1.0, 15, True),
]


def seed_examples() -> list[tuple[dict, int]]:
    def make(row, label):
        title, description, price, rooms, surface, is_private = row
        is_private = is_private or label == 1  # these scams are posted as private landlords
        category = "SHARED" if surface and surface < 20 else "APARTMENT"
        return {
            "title": title, "description": description, "price": price, "rooms": rooms, "surface": surface,
            "category": category, "is_private": is_private, "city": "Bern", "address": None,
        }, label

    return [make(row, 1) for row in SCAMS] + [make(row, 0) for row in LEGIT]

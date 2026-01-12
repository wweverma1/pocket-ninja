import random

JAPANESE_FOOD_USERNAMES = [
    "sushi_samurai", "ramen_ronin", "soba_sensei", "udon_unicorn", "tempura_tycoon",
    "wasabi_warrior", "sashimi_shogun", "miso_master", "gyoza_guru", "yakitori_yum",
    "tonkatsu_tiger", "shabu_shabu_chef", "sukiyaki_star", "karaage_king", "korokke_kid",
    "bento_boss", "onigiri_original", "takoyaki_tornado", "okonomi_otaku", "unagi_unity",
    "katsu_curry_captain", "omurice_origin", "hayashi_hero", "napolitan_nom", "donburi_dreamer",

    "dashi_dude", "shoyu_shadow", "ponzu_pal", "yuzu_youth", "sesame_snap",
    "goma_gold", "shiso_chic", "nori_ninja", "umeboshi_ultra", "katsuobushi_kid",
    "tofu_titan", "natto_nomad", "edamame_eater", "menma_master", "chashu_champ",
    "ajitama_ace", "narutomaki_fan", "wakame_wave", "moyashi_mood", "benishoga_boy",
    "wagyu_wonder", "kobe_beef_boss", "uni_universe", "ikura_icon", "maguro_mate",
    "ebi_enthusiast", "scallop_scout", "tako_time", "ika_ink", "anago_angel",

    "matcha_mama", "hojicha_hero", "sencha_sipper", "genmaicha_guru", "sakura_sweets",
    "mochi_moon", "daifuku_dream", "dango_doctor", "taiyaki_tail", "dorayaki_don",
    "anmitsu_angel", "kakigori_cool", "purin_prince", "castella_cake", "melonpan_mania",
    "anko_addict", "kinako_kick", "warabimochi_win", "yokan_yumm", "monaka_mood",
    "crepe_harajuku", "fluffy_pancake_fan", "konbini_sweets", "pocky_pocket", "kitkat_collector",

    "umami_user", "oishii_observer", "itadakimasu_ian", "gochisosama_gal", "kuidaore_kid",
    "izakaya_insider", "kaiseki_king", "yatai_yeller", "depachika_diver", "kuten_cruiser",
    "barikata_boy", "kaedama_kid", "tsukemen_titan", "mazesoba_maze", "abura_soba_ace",

    "hokkaido_hungry", "sapporo_soup"
]


def get_random_username():
    return random.choice(JAPANESE_FOOD_USERNAMES)

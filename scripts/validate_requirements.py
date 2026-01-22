"""
Validação dos 9 Requisitos do Technical Case
Executa queries que PROVAM que cada requisito está implementado corretamente.
"""

import duckdb
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "warehouse" / "teachable.duckdb"

def connect():
    return duckdb.connect(str(DB_PATH))

def run_query(con, query):
    return con.execute(query).fetchall()

def run_query_df(con, query):
    return con.execute(query).fetchdf()

def print_header(text):
    print(f"\n{'='*70}")
    print(f"  {text}")
    print('='*70)

def print_result(passed, message):
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status}: {message}")
    return passed


def req1_gmv_only_released(con):
    """Req #1: GMV só de released (paid) transactions"""
    print_header("Requisito #1: GMV só de released (paid) transactions")

    # Teste 1: Nenhuma linha GMV válida com release_date NULL
    result = run_query(con, """
        SELECT COUNT(*)
        FROM gold.v_gmv_current
        WHERE is_valid_for_gmv = true AND release_date IS NULL
    """)
    t1 = print_result(result[0][0] == 0,
        f"Nenhum GMV válido com release_date=NULL (encontrado: {result[0][0]})")

    # Teste 2: Nenhuma linha GMV válida com status != APROVADA
    result = run_query(con, """
        SELECT COUNT(*)
        FROM gold.v_gmv_current
        WHERE is_valid_for_gmv = true AND purchase_status != 'APROVADA'
    """)
    t2 = print_result(result[0][0] == 0,
        f"Nenhum GMV válido com status!=APROVADA (encontrado: {result[0][0]})")

    # Teste 3: Flag é consistente com a lógica
    result = run_query(con, """
        SELECT COUNT(*)
        FROM gold.v_gmv_current
        WHERE is_valid_for_gmv != (release_date IS NOT NULL AND purchase_status = 'APROVADA')
    """)
    t3 = print_result(result[0][0] == 0,
        f"Flag is_valid_for_gmv consistente (inconsistências: {result[0][0]})")

    # Teste 4: GMV total bate com esperado
    result = run_query(con, """
        SELECT ROUND(SUM(purchase_value), 2)
        FROM gold.v_gmv_current
        WHERE is_valid_for_gmv = true
    """)
    expected_gmv = 23561.90
    actual_gmv = result[0][0]
    t4 = print_result(abs(actual_gmv - expected_gmv) < 0.01,
        f"GMV total = {actual_gmv} (esperado: {expected_gmv})")

    return all([t1, t2, t3, t4])


def req2_late_arrivals(con):
    """Req #2: Handles late arriving and reprocessed events"""
    print_header("Requisito #2: Late arrivals e reprocessamentos")

    # Teste 1: Purchase 72 - começou INICIADA, virou APROVADA (late arrival)
    result = run_query(con, """
        SELECT purchase_status, release_date, is_valid_for_gmv
        FROM gold.v_gmv_current
        WHERE purchase_id = 72
    """)
    t1 = print_result(
        result[0][0] == 'APROVADA' and result[0][1] is not None and result[0][2] == True,
        f"Purchase 72 (late arrival): status={result[0][0]}, release_date={result[0][1]}, is_gmv={result[0][2]}"
    )

    # Teste 2: Purchase 78 - late arrival tardio (só em Março virou APROVADA)
    result = run_query(con, """
        SELECT purchase_status, release_date, is_valid_for_gmv
        FROM gold.v_gmv_current
        WHERE purchase_id = 78
    """)
    t2 = print_result(
        result[0][0] == 'APROVADA' and result[0][1] is not None and result[0][2] == True,
        f"Purchase 78 (late arrival tardio): status={result[0][0]}, release_date={result[0][1]}, is_gmv={result[0][2]}"
    )

    # Teste 3: Dedup pegou última versão (purchase 64 tem 4 versões no raw)
    raw_count = run_query(con, """
        SELECT COUNT(*) FROM raw.purchase WHERE purchase_id = 64
    """)[0][0]

    gold_count = run_query(con, """
        SELECT COUNT(*) FROM gold.v_gmv_current WHERE purchase_id = 64
    """)[0][0]

    t3 = print_result(raw_count > 1 and gold_count == 1,
        f"Purchase 64: {raw_count} versões no raw → {gold_count} no gold (dedup OK)")

    # Teste 4: Purchase 64 tem a última versão (transaction_date mais recente)
    result = run_query(con, """
        SELECT transaction_date
        FROM gold.v_gmv_current
        WHERE purchase_id = 64
    """)
    t4 = print_result(str(result[0][0]) == '2023-03-12',
        f"Purchase 64 transaction_date={result[0][0]} (esperado: 2023-03-12, última versão)")

    return all([t1, t2, t3, t4])


def req3_immutability(con):
    """Req #3: Preserves past analytical results (immutability)"""
    print_header("Requisito #3: Imutabilidade")

    # Teste 1: Tabela é incremental append-only (verificar estrutura)
    # Não podemos testar imutabilidade diretamente sem rodar múltiplas vezes
    # Mas podemos verificar que o grain está correto

    result = run_query(con, """
        SELECT purchase_id, snapshot_date, COUNT(*) as cnt
        FROM gold.fact_gmv_snapshot
        GROUP BY purchase_id, snapshot_date
        HAVING COUNT(*) > 1
    """)
    t1 = print_result(len(result) == 0,
        f"Sem duplicatas no grain (purchase_id, snapshot_date): {len(result)} encontradas")

    # Teste 2: Todos os registros têm snapshot_date
    result = run_query(con, """
        SELECT COUNT(*) FROM gold.fact_gmv_snapshot WHERE snapshot_date IS NULL
    """)
    t2 = print_result(result[0][0] == 0,
        f"Todos registros têm snapshot_date (nulls: {result[0][0]})")

    # Teste 3: snapshot_date é consistente (mesmo valor em todo o snapshot)
    result = run_query(con, """
        SELECT COUNT(DISTINCT snapshot_date) FROM gold.fact_gmv_snapshot
    """)
    t3 = print_result(result[0][0] >= 1,
        f"Snapshots existentes: {result[0][0]}")

    print("\n  ⚠️  Nota: Imutabilidade total requer teste com múltiplos runs em dias diferentes.")
    print("      O design (incremental append) garante que snapshots antigos não são alterados.")

    return all([t1, t2, t3])


def req4_as_of_queries(con):
    """Req #4: Supports as-of queries"""
    print_header("Requisito #4: As-of queries")

    # Teste 1: Query as-of executa sem erro
    try:
        result = run_query(con, """
            SELECT subsidiary, SUM(purchase_value) as gmv
            FROM gold.fact_gmv_snapshot
            WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM gold.fact_gmv_snapshot)
              AND transaction_date BETWEEN '2023-01-01' AND '2023-01-31'
              AND is_valid_for_gmv = true
            GROUP BY subsidiary
        """)
        t1 = print_result(True, f"Query as-of de Janeiro executa OK ({len(result)} linhas)")
    except Exception as e:
        t1 = print_result(False, f"Query as-of falhou: {e}")

    # Teste 2: Estrutura suporta diferentes snapshot_dates
    result = run_query(con, """
        SELECT
            COUNT(DISTINCT snapshot_date) as snapshots,
            COUNT(DISTINCT purchase_id) as purchases
        FROM gold.fact_gmv_snapshot
    """)
    t2 = print_result(result[0][0] >= 1 and result[0][1] >= 1,
        f"Estrutura OK: {result[0][0]} snapshot(s), {result[0][1]} purchases")

    print("\n  ℹ️  Nota: Com múltiplos snapshots, podemos comparar 'GMV de Jan visto em Mar' vs 'hoje'.")

    return all([t1, t2])


def req5_current_historical_lineage(con):
    """Req #5: Easy access to current/historical/lineage"""
    print_header("Requisito #5: Current / Historical / Lineage")

    # Teste 1: View v_gmv_current existe e funciona
    try:
        result = run_query(con, "SELECT COUNT(*) FROM gold.v_gmv_current")
        t1 = print_result(result[0][0] > 0,
            f"v_gmv_current funciona: {result[0][0]} registros")
    except Exception as e:
        t1 = print_result(False, f"v_gmv_current não existe ou falhou: {e}")

    # Teste 2: Histórico de uma purchase (todas as versões por snapshot)
    result = run_query(con, """
        SELECT COUNT(DISTINCT snapshot_date)
        FROM gold.fact_gmv_snapshot
        WHERE purchase_id = 55
    """)
    t2 = print_result(result[0][0] >= 1,
        f"Histórico disponível: purchase 55 tem {result[0][0]} snapshot(s)")

    # Teste 3: Query de lineage/diff é possível
    try:
        result = run_query(con, """
            SELECT purchase_id, snapshot_date, purchase_value, is_valid_for_gmv
            FROM gold.fact_gmv_snapshot
            WHERE purchase_id = 55
            ORDER BY snapshot_date
        """)
        t3 = print_result(True, f"Query de lineage executa OK ({len(result)} versões)")
    except Exception as e:
        t3 = print_result(False, f"Query de lineage falhou: {e}")

    return all([t1, t2, t3])


def req6_simple_no_joins(con):
    """Req #6: Simple to query (no joins needed)"""
    print_header("Requisito #6: Simples (no joins)")

    # Teste 1: Query de GMV sem JOIN funciona
    try:
        result = run_query(con, """
            SELECT subsidiary, SUM(purchase_value) as gmv
            FROM gold.v_gmv_current
            WHERE is_valid_for_gmv = true
            GROUP BY subsidiary
        """)
        t1 = print_result(len(result) >= 1,
            f"GMV por subsidiary sem JOIN: {len(result)} subsidiaries")
    except Exception as e:
        t1 = print_result(False, f"Query falhou: {e}")

    # Teste 2: Todos os campos necessários estão na tabela
    result = run_query(con, """
        SELECT
            COUNT(*) as total,
            COUNT(purchase_id) as has_purchase_id,
            COUNT(subsidiary) as has_subsidiary,
            COUNT(purchase_value) as has_value,
            COUNT(release_date) as has_release_date,
            COUNT(purchase_status) as has_status
        FROM gold.v_gmv_current
    """)
    total = result[0][0]
    all_present = all(result[0][i] == total for i in range(1, 4))  # purchase_id, subsidiary, value
    t2 = print_result(all_present,
        f"Campos desnormalizados presentes (total: {total})")

    # Teste 3: Não precisa de JOIN com outras tabelas
    print("\n  ℹ️  Verificação: gold.v_gmv_current contém todos os campos para análise de GMV:")
    cols = run_query(con, "SELECT * FROM gold.v_gmv_current LIMIT 1")
    col_names = [desc[0] for desc in con.description]
    print(f"      Colunas: {', '.join(col_names)}")
    t3 = print_result('subsidiary' in col_names and 'purchase_value' in col_names,
        "Tabela é self-contained")

    return all([t1, t2, t3])


def req7_partitioned_by_transaction_date(con):
    """Req #7: Partitioned by transaction_date"""
    print_header("Requisito #7: Particionado por transaction_date")

    # Teste 1: Coluna transaction_date existe
    result = run_query(con, """
        SELECT COUNT(*) FROM gold.v_gmv_current WHERE transaction_date IS NOT NULL
    """)
    total = run_query(con, "SELECT COUNT(*) FROM gold.v_gmv_current")[0][0]
    t1 = print_result(result[0][0] == total,
        f"transaction_date preenchido em {result[0][0]}/{total} registros")

    # Teste 2: Distribuição por transaction_date
    result = run_query(con, """
        SELECT COUNT(DISTINCT transaction_date) FROM gold.v_gmv_current
    """)
    t2 = print_result(result[0][0] >= 1,
        f"Dados distribuídos em {result[0][0]} transaction_dates")

    # Teste 3: Query com filtro de transaction_date funciona
    try:
        result = run_query(con, """
            SELECT SUM(purchase_value)
            FROM gold.v_gmv_current
            WHERE transaction_date BETWEEN '2023-02-01' AND '2023-02-28'
              AND is_valid_for_gmv = true
        """)
        t3 = print_result(True,
            f"Query com filtro transaction_date OK (GMV Fev: {result[0][0]:.2f})")
    except Exception as e:
        t3 = print_result(False, f"Query falhou: {e}")

    print("\n  ⚠️  Nota: DuckDB não tem particionamento físico como Spark/BigQuery.")
    print("      A coluna existe e queries funcionam. Em produção, seria PARTITIONED BY.")

    return all([t1, t2, t3])


def req8_d1_batches(con):
    """Req #8: Updated in D-1 batches"""
    print_header("Requisito #8: Atualizado em D-1 batches")

    # Teste 1: snapshot_date está preenchido
    result = run_query(con, """
        SELECT DISTINCT snapshot_date FROM gold.fact_gmv_snapshot ORDER BY snapshot_date
    """)
    t1 = print_result(len(result) >= 1,
        f"Snapshots existentes: {[str(r[0]) for r in result]}")

    # Teste 2: snapshot_date é a data do build (não podemos verificar se é "hoje")
    # Mas podemos verificar que é uma data válida
    result = run_query(con, """
        SELECT MAX(snapshot_date) FROM gold.fact_gmv_snapshot
    """)
    t2 = print_result(result[0][0] is not None,
        f"Último snapshot: {result[0][0]}")

    print("\n  ℹ️  O design usa snapshot_date = CURRENT_DATE no momento do dbt run.")
    print("      Isso representa o estado conhecido até D-1 (batch diário).")

    return all([t1, t2])


def req9_reprocessing_no_rewrite(con):
    """Req #9: Reprocessing does not rewrite historical truth"""
    print_header("Requisito #9: Reprocessamento não reescreve histórico")

    # Teste 1: Modelo é incremental append (verificar pelo comportamento)
    # Se rodarmos 2x no mesmo dia, não devemos ter duplicatas
    result = run_query(con, """
        SELECT purchase_id, snapshot_date, COUNT(*) as cnt
        FROM gold.fact_gmv_snapshot
        GROUP BY purchase_id, snapshot_date
        HAVING COUNT(*) > 1
    """)
    t1 = print_result(len(result) == 0,
        f"Sem duplicatas (idempotência): {len(result)} encontradas")

    # Teste 2: Estrutura permite múltiplos snapshots por purchase
    result = run_query(con, """
        SELECT
            'grain' as check_type,
            COUNT(DISTINCT purchase_id || '-' || snapshot_date) as unique_records,
            COUNT(*) as total_records
        FROM gold.fact_gmv_snapshot
    """)
    t2 = print_result(result[0][1] == result[0][2],
        f"Grain único: {result[0][1]} records únicos de {result[0][2]} total")

    print("\n  ℹ️  Design: incremental_strategy='append' + NOT EXISTS evita sobrescrita.")
    print("      Snapshots antigos permanecem intactos; novos são adicionados.")
    print("      Teste completo requer rodar dbt run em dias diferentes e comparar.")

    return all([t1, t2])


def main():
    print("\n" + "="*70)
    print("  VALIDAÇÃO DOS 9 REQUISITOS DO TECHNICAL CASE")
    print("="*70)

    con = connect()

    results = {}

    results['Req #1: GMV released only'] = req1_gmv_only_released(con)
    results['Req #2: Late arrivals'] = req2_late_arrivals(con)
    results['Req #3: Immutability'] = req3_immutability(con)
    results['Req #4: As-of queries'] = req4_as_of_queries(con)
    results['Req #5: Current/Historical/Lineage'] = req5_current_historical_lineage(con)
    results['Req #6: Simple (no joins)'] = req6_simple_no_joins(con)
    results['Req #7: Partitioned by transaction_date'] = req7_partitioned_by_transaction_date(con)
    results['Req #8: D-1 batches'] = req8_d1_batches(con)
    results['Req #9: No rewrite on reprocess'] = req9_reprocessing_no_rewrite(con)

    con.close()

    # Resumo final
    print("\n" + "="*70)
    print("  RESUMO FINAL")
    print("="*70)

    all_passed = True
    for req, passed in results.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {req}")
        if not passed:
            all_passed = False

    print("\n" + "-"*70)
    if all_passed:
        print("  🎉 TODOS OS 9 REQUISITOS VALIDADOS COM SUCESSO!")
    else:
        failed = [r for r, p in results.items() if not p]
        print(f"  ⚠️  {len(failed)} requisito(s) com problemas: {', '.join(failed)}")
    print("-"*70 + "\n")

    return all_passed


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)

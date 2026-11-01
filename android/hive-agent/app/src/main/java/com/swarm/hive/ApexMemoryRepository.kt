package com.swarm.hive

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper

/**
 * ApexMemoryRepository — SQLite conversation state for the APEX node.
 *
 * DEOS architectural exception: this class is exempt from the 40-line limit
 * so the schema and every query live in one place.
 *
 * APEX keeps no context of its own. Every request is rebuilt from this table,
 * and only the newest [HISTORY_LIMIT] rows per session are ever read back so
 * the prompt (and KV cache) stays small on the 16 GB RX 6800.
 */
class ApexMemoryRepository(ctx: Context) :
    SQLiteOpenHelper(ctx.applicationContext, DB_NAME, null, DB_VERSION) {

    data class StoredMessage(
        val id: Long,
        val sessionId: String,
        val role: String,
        val content: String,
        val timestamp: String,
    )

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(SQL_CREATE_TABLE)
        db.execSQL(SQL_CREATE_INDEX)
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        // Schema v1 only. Future versions must migrate here, never drop history.
        onCreate(db)
    }

    /** Appends one message. Returns the new row id. */
    fun insertMessage(sessionId: String, role: String, content: String): Long {
        require(sessionId.isNotBlank()) { "sessionId must not be blank" }
        require(role in ALLOWED_ROLES) { "role must be one of $ALLOWED_ROLES, got '$role'" }
        val values = ContentValues().apply {
            put(COL_SESSION_ID, sessionId)
            put(COL_ROLE, role)
            put(COL_CONTENT, content)
        }
        return writableDatabase.insertOrThrow(TABLE_MESSAGES, null, values)
    }

    /**
     * Newest [limit] messages for [sessionId], returned oldest-first so they
     * can be appended to a payload in conversational order. Ordered by `id`
     * (not `timestamp`) because CURRENT_TIMESTAMP only has 1 s resolution.
     */
    fun lastTurns(sessionId: String, limit: Int = HISTORY_LIMIT): List<StoredMessage> {
        val out = ArrayList<StoredMessage>(limit)
        readableDatabase.rawQuery(SQL_LAST_TURNS, arrayOf(sessionId, limit.toString())).use { c ->
            while (c.moveToNext()) {
                out.add(
                    StoredMessage(
                        id = c.getLong(0),
                        sessionId = c.getString(1),
                        role = c.getString(2),
                        content = c.getString(3),
                        timestamp = c.getString(4),
                    )
                )
            }
        }
        return out
    }

    companion object {
        const val DB_NAME = "apex_memory.db"
        const val DB_VERSION = 1
        const val HISTORY_LIMIT = 5

        const val ROLE_SYSTEM = "system"
        const val ROLE_USER = "user"
        const val ROLE_ASSISTANT = "assistant"
        val ALLOWED_ROLES = setOf(ROLE_SYSTEM, ROLE_USER, ROLE_ASSISTANT)

        private const val TABLE_MESSAGES = "messages"
        private const val COL_ID = "id"
        private const val COL_SESSION_ID = "session_id"
        private const val COL_ROLE = "role"
        private const val COL_CONTENT = "content"
        private const val COL_TIMESTAMP = "timestamp"

        private const val SQL_CREATE_TABLE =
            "CREATE TABLE IF NOT EXISTS $TABLE_MESSAGES (" +
                "$COL_ID INTEGER PRIMARY KEY, " +
                "$COL_SESSION_ID TEXT NOT NULL, " +
                "$COL_ROLE TEXT NOT NULL, " +
                "$COL_CONTENT TEXT NOT NULL, " +
                "$COL_TIMESTAMP DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"

        private const val SQL_CREATE_INDEX =
            "CREATE INDEX IF NOT EXISTS idx_messages_session_id " +
                "ON $TABLE_MESSAGES ($COL_SESSION_ID, $COL_ID)"

        private const val SQL_LAST_TURNS =
            "SELECT $COL_ID, $COL_SESSION_ID, $COL_ROLE, $COL_CONTENT, $COL_TIMESTAMP FROM (" +
                "SELECT * FROM $TABLE_MESSAGES WHERE $COL_SESSION_ID = ? " +
                "ORDER BY $COL_ID DESC LIMIT ?" +
                ") ORDER BY $COL_ID ASC"
    }
}
